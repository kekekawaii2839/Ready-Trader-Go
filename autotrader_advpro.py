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

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, Side, MAXIMUM_ASK, MINIMUM_BID

import numpy as np

LOT_SIZE = 10
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS


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
        self.value = 0
        self.fut_vwap = self.fut_prev_vwap = self.prev_fut_return = 0
        self.delta = 0
        self.etf_price = self.fut_price = 0
        #for vwap
        self.vwap_list = list()
        self.history_price = list()
        self.history_volume = list()
        self.time = [0]
        #for slopes
        self.a = list()
        self.b = list()
        self.poly = np.poly1d([0])
        self.history_price_aver = list()

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        if client_order_id != 0:
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled, partially or fully.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.

        If the order was unsuccessful, both the price and volume will be zero.
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
        self.value = self.position * self.etf_price + self.fut_position * self.fut_price

        self.history_price.append((ask_prices[0]+bid_prices[0])/2)
        self.history_volume.append(ask_volumes[0]+bid_volumes[0])
        if len(self.history_price) > 5:
            self.history_price_aver.append(sum(self.history_price[-5:])/5)

        #calculate VWAP
        s = s2 = 0
        for i in range(-1,-min(len(self.history_price),24),-1):
            s += self.history_price[i] * self.history_volume[i]
            s2 += self.history_volume[i]
        if s2 == 0:
            vwap = 0
        else:
            vwap = int(s/s2)
        self.vwap_list.append(vwap)

        self.time.append(self.time[-1]+1)

        #calculate slopes
        if len(self.time) > 5:
            self.a = self.time[-5:]
            self.b = self.vwap_list[-5:]
            params = np.polyfit(self.a,self.b,1)
            self.poly = np.poly1d(params)
            print("slope=",self.poly[1])
        slope = self.poly[1]
        
        if bid_volumes[0] + ask_volumes[0] == 0:
            return
        if instrument == Instrument.FUTURE:
            self.fut_prev_vwap = self.fut_vwap
            self.fut_vwap = (bid_prices[0] * ask_volumes[0] + ask_prices[0] * bid_volumes[0]) / (
                    bid_volumes[0] + ask_volumes[0])
            self.fut_price = (ask_prices[0]+bid_prices[0])/2
        if instrument == Instrument.ETF:
            self.etf_price = (ask_prices[0]+bid_prices[0])/2
            vwap = (bid_prices[0] * ask_volumes[0] + ask_prices[0] * bid_volumes[0]) / (bid_volumes[0] + ask_volumes[0])
            if vwap == 0:
                return
            pos_adj = -0.7 * self.position / 100 * TICK_SIZE_IN_CENTS
            # Used for return signal
            fut_return = (self.fut_vwap - self.fut_prev_vwap) / self.fut_prev_vwap * TICK_SIZE_IN_CENTS + self.prev_fut_return * 0.6 if self.fut_prev_vwap != 0 else 0
            self.prev_fut_return = fut_return

            slope_adj = int(100 * slope) //TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
            new_bid_price = int((vwap + pos_adj + fut_return * 100) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS) - 200 + slope_adj
            new_ask_price = new_bid_price + slope_adj
            print(self.fut_price/100, self.etf_price/100, self.value/100)

            if self.bid_id != 0 and new_bid_price not in (self.bid_price, 0):
                self.send_cancel_order(self.bid_id)
                self.bid_id = 0
            if self.ask_id != 0 and new_ask_price not in (self.ask_price, 0):
                self.send_cancel_order(self.ask_id)
                self.ask_id = 0

            if self.bid_id == 0 and new_bid_price != 0 and self.position + 2*LOT_SIZE < POSITION_LIMIT:
                self.bid_id = next(self.order_ids)
                self.bid_price = new_bid_price
                self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.bid_id)

            if self.ask_id == 0 and new_ask_price != 0 and self.position - 2*LOT_SIZE > -POSITION_LIMIT:
                self.ask_id = next(self.order_ids)
                self.ask_price = new_ask_price
                self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.ask_id)

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when when of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received order filled for order %d with price %d and volume %d", client_order_id,
                         price, volume)

        self.value = self.position * self.etf_price + self.fut_position * self.fut_price

        if client_order_id in self.bids:
            self.position += volume
            self.fut_ask_id = next(self.order_ids)
            self.send_hedge_order(self.fut_ask_id, Side.ASK, MIN_BID_NEAREST_TICK, volume)#int(self.value / self.fut_price)
            self.fut_asks.add(self.fut_ask_id)
        elif client_order_id in self.asks:
            self.position -= volume
            self.fut_bid_id = next(self.order_ids)
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
        self.logger.info("received trade ticks for instrument %d with sequence number %d", instrument, sequence_number)
