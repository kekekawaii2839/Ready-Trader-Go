# Copyright 2021 Optiver Asia Pacific Pty. Ltd.
#
# This file is part of Ready Trader Go.
#
#     Ready Trader Go is free software: you can redistribute it and/or
#     modify it under the terms of the GNU Affero General Public License
#     as published by the Free Software Foundation, either version 3 of
#     the License, or (at your option) any later version.
#
#     Ready Trader Go is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with Ready Trader Go.  If not, see
#     <https://www.gnu.org/licenses/>.
import asyncio
import itertools

from typing import List

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, MAXIMUM_ASK, MINIMUM_BID, Side

import numpy as np

LOT_SIZE2 = 20
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
OFFSET1 = 40
OFFSET2 = 100


class AutoTrader(BaseAutoTrader):
    """Example Auto-trader.

    When it starts this auto-trader places ten-lot bid and ask orders at the
    current best-bid and best-ask prices respectively. Thereafter, if it has
    a long position (it has bought more lots than it has sold) it reduces its
    bid and ask prices. Conversely, if it has a short position (it has sold
    more lots than it has bought) then it increases its bid and ask prices.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = set()
        self.asks = set()
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        self.fut_bids = set()
        self.fut_asks = set()
        self.fut_ask_id = self.fut_bid_id = self.fut_position = 0
        #
        self.etf_price = list()
        self.fut_price = list()
        self.delta = list()
        self.upper_rail1 = 0
        self.upper_rail2 = 0
        self.lower_rail1 = 0
        self.lower_rail2 = 0
        #
        self.last_bid_price1 = self.last_bid_id1 = 0
        self.last_bid_price2 = self.last_bid_id2 = 0
        self.last_ask_price1 = self.last_ask_id1 = 0
        self.last_ask_price2 = self.last_ask_id2 = 0
        #
        self.LOT_SIZE1 = 10
        #
        self.slope = 0
        self.time = list()
        self.current_time = itertools.count(1)
        self.position_history = list()
        self.mode = 0  #0 for normal, 1 for trend
        self.timestamp = 0
        self.price_compare = list()

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        if client_order_id != 0 and (client_order_id in self.bids or client_order_id in self.asks):
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received hedge filled for order %d with average price %d and volume %d", client_order_id,
                         price, volume)
        if client_order_id in self.fut_bids:
            self.fut_position += volume
        elif client_order_id in self.fut_asks:
            self.fut_position -= volume

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        self.logger.info("received order book for instrument %d with sequence number %d", instrument,
                         sequence_number)

        if ask_prices[0] == 0 or bid_prices[0] == 0:
            return
        if ask_volumes[0] + bid_volumes[0] == 0:
            return

        if instrument == Instrument.ETF:
            self.etf_price.append((ask_prices[0] + bid_prices[0]) / 2)
            self.time.append(int(next(self.current_time)))
            self.position_history.append(self.position)
        if instrument == Instrument.FUTURE:
            self.fut_price.append((ask_prices[0] + bid_prices[0]) / 2)

        #switch mode
        self.price_compare.append(np.average(self.etf_price[-40:]) < np.average(self.fut_price[-40:]))
        #print(self.price_compare[-1])
        pos_std = np.std(self.position_history[-52:])
        print(pos_std)
        self.mode = 0
        if abs(pos_std) < 12:
            temp = self.price_compare[-1]
            flag = True
            print(self.price_compare[-8:-2])
            for i in self.price_compare[-8:-2]:
                if temp != i:
                    flag = False
                    break
            if flag and len(self.price_compare) > 36:  #for stablity
                if self.timestamp != 0 and self.timestamp + 40 * 8 > self.time[-1]:
                    self.mode = 1
                if self.timestamp == 0:
                    self.mode = 1
                    self.timestamp = self.time[-1]
            if self.timestamp + 40 * 8 <= self.time[-1]:
                self.mode = self.timestamp = 0
        else:
            self.mode = self.timestamp = 0
        print("timestamp=",self.timestamp)
        print("mode=",self.mode)

        if len(self.etf_price) > 0 and len(self.fut_price) > 0:
            self.delta.append(self.etf_price[-1] - self.fut_price[-1])
            std = np.std(self.delta)
            self.upper_rail1 = std + OFFSET1
            self.upper_rail2 = std + OFFSET2
            self.lower_rail1 = -std - OFFSET1
            self.lower_rail2 = -std - OFFSET2

        if self.mode == 0:
            #check if hedged
            if self.fut_position + self.position > 5:
                self.fut_ask_id = next(self.order_ids)
                self.send_hedge_order(self.fut_ask_id, Side.ASK, MIN_BID_NEAREST_TICK, 1)
                self.fut_asks.add(self.fut_ask_id)
            elif self.fut_position + self.position < -5:
                self.fut_bid_id = next(self.order_ids)
                self.send_hedge_order(self.fut_bid_id, Side.BID, MAX_ASK_NEAREST_TICK, 1)
                self.fut_bids.add(self.fut_bid_id)
        
        elif self.mode == 1:  #follow the trend
            params = np.polyfit(self.time[-48:],self.etf_price[-48:],1)
            poly = np.poly1d(params)
            slope = poly[1]
            if self.fut_position > 0 and slope < -15 and self.fut_position - 10 > -POSITION_LIMIT:
                self.fut_ask_id = next(self.order_ids)
                self.send_hedge_order(self.fut_ask_id, Side.ASK, MIN_BID_NEAREST_TICK, 10)
                self.fut_asks.add(self.fut_ask_id)
            elif self.fut_position < 0 and slope > 15 and self.fut_position + 10 < POSITION_LIMIT:
                self.fut_bid_id = next(self.order_ids)
                self.send_hedge_order(self.fut_bid_id, Side.BID, MAX_ASK_NEAREST_TICK, 10)
                self.fut_bids.add(self.fut_bid_id)
        
        if instrument == Instrument.ETF:
            new_bid_price1 = int(self.lower_rail1 + self.fut_price[-1]) // 100 * 100
            new_ask_price1 = int(self.upper_rail1 + self.fut_price[-1]) // 100 * 100
            new_bid_price2 = int(self.lower_rail2 + self.fut_price[-1]) // 100 * 100
            new_ask_price2 = int(self.upper_rail2 + self.fut_price[-1]) // 100 * 100

            if self.last_bid_id1 != 0 and (new_bid_price1 not in (self.last_bid_price1, 0) or ask_prices[0] <= new_bid_price2):
                self.send_cancel_order(self.last_bid_id1)
                self.last_bid_id1 = 0

            if self.last_bid_id2 != 0 and new_bid_price2 not in (self.last_bid_price2, 0):
                self.send_cancel_order(self.last_bid_id2)
                self.last_bid_id2 = 0

            if self.last_ask_id1 != 0 and (new_ask_price1 not in (self.last_ask_price1, 0) or bid_prices[0] >= new_ask_price2):
                self.send_cancel_order(self.last_ask_id1)
                self.last_ask_id1 = 0

            if self.last_ask_id2 != 0 and new_ask_price2 not in (self.last_ask_price2, 0):
                self.send_cancel_order(self.last_ask_id2)
                self.last_ask_id2 = 0

            if self.last_bid_id1 == 0 and new_bid_price1 != 0 and self.position + self.LOT_SIZE1 + LOT_SIZE2 < POSITION_LIMIT and ask_prices[0] > new_bid_price2:
                self.last_bid_id1 = next(self.order_ids)
                self.last_bid_price1 = new_bid_price1
                self.send_insert_order(self.last_bid_id1, Side.BUY, new_bid_price1, self.LOT_SIZE1, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.last_bid_id1)

            if self.last_bid_id2 == 0 and new_bid_price2 != 0 and self.position + self.LOT_SIZE1 + LOT_SIZE2 < POSITION_LIMIT:
                self.last_bid_id2 = next(self.order_ids)
                self.last_bid_price2 = new_bid_price2
                self.send_insert_order(self.last_bid_id2, Side.BUY, new_bid_price2, LOT_SIZE2, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.last_bid_id2)

            if self.last_ask_id1 == 0 and new_ask_price1 != 0 and self.position - self.LOT_SIZE1 - LOT_SIZE2 > -POSITION_LIMIT and bid_prices[0] < new_ask_price2:
                self.last_ask_id1 = next(self.order_ids)
                self.last_ask_price1 = new_ask_price1
                self.send_insert_order(self.last_ask_id1, Side.SELL, new_ask_price1, self.LOT_SIZE1, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.last_ask_id1)

            if self.last_ask_id2 == 0 and new_ask_price2 != 0 and self.position - self.LOT_SIZE1 - LOT_SIZE2 > -POSITION_LIMIT:
                self.last_ask_id2 = next(self.order_ids)
                self.last_ask_price2 = new_ask_price2
                self.send_insert_order(self.last_ask_id2, Side.SELL, new_ask_price2, LOT_SIZE2, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.last_ask_id2)

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received order filled for order %d with price %d and volume %d", client_order_id,
                         price, volume)
        if client_order_id in self.bids:
            self.position += volume
            self.fut_ask_id = next(self.order_ids)
            self.LOT_SIZE1 = min(10, POSITION_LIMIT - abs(self.position) - LOT_SIZE2)
            if self.LOT_SIZE1 < 0:
                self.LOT_SIZE1 = 0
            self.send_hedge_order(self.fut_ask_id, Side.ASK, MIN_BID_NEAREST_TICK, volume)
            self.fut_asks.add(self.fut_ask_id)
        elif client_order_id in self.asks:
            self.position -= volume
            self.fut_bid_id = next(self.order_ids)
            self.LOT_SIZE1 = min(10, POSITION_LIMIT - abs(self.position) - LOT_SIZE2)
            if self.LOT_SIZE1 < 0:
                self.LOT_SIZE1 = 0
            self.send_hedge_order(self.fut_bid_id, Side.BID, MAX_ASK_NEAREST_TICK, volume)
            self.fut_bids.add(self.fut_bid_id)

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        self.logger.info("received order status for order %d with fill volume %d remaining %d and fees %d",
                         client_order_id, fill_volume, remaining_volume, fees)
        if remaining_volume == 0:
            if client_order_id == self.bid_id:
                self.bid_id = 0
            elif client_order_id == self.ask_id:
                self.ask_id = 0

            # It could be either a bid or an ask
            self.bids.discard(client_order_id)
            self.asks.discard(client_order_id)

    def on_trade_ticks_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                               ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically when there is trading activity on the market.

        The five best ask (i.e. sell) and bid (i.e. buy) prices at which there
        has been trading activity are reported along with the aggregated volume
        traded at each of those price levels.

        If there are less than five prices on a side, then zeros will appear at
        the end of both the prices and volumes arrays.
        """
        self.logger.info("received trade ticks for instrument %d with sequence number %d", instrument,
                         sequence_number)
