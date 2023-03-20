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

LOT_SIZE1 = 20
LOT_SIZE2 = 60
POSITION_LIMIT = 80
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
OFFSET1 = 100
OFFSET2 = 300


class AutoTrader(BaseAutoTrader):

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = set()
        self.asks = set()
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
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
        self.bid_lot_size1 = LOT_SIZE1
        self.bid_lot_size2 = LOT_SIZE2
        self.ask_lot_size1 = LOT_SIZE1
        self.ask_lot_size2 = LOT_SIZE2
        self.bid_lot_size1_pre = LOT_SIZE1
        self.bid_lot_size2_pre = LOT_SIZE2
        self.ask_lot_size1_pre = LOT_SIZE1
        self.ask_lot_size2_pre = LOT_SIZE2

    def update_lot_sizes(self) -> None:
        self.bid_lot_size1_pre = self.bid_lot_size1
        self.bid_lot_size2_pre = self.bid_lot_size2
        self.ask_lot_size1_pre = self.ask_lot_size1
        self.ask_lot_size2_pre = self.ask_lot_size2
        self.bid_lot_size1 = min(LOT_SIZE1, POSITION_LIMIT - self.position - LOT_SIZE2)
        self.ask_lot_size1 = min(LOT_SIZE1, POSITION_LIMIT + self.position - LOT_SIZE2)
        self.bid_lot_size2 = min(LOT_SIZE2, POSITION_LIMIT - self.position)
        self.ask_lot_size2 = min(LOT_SIZE2, POSITION_LIMIT + self.position)
        """if self.bid_lot_size1_pre > self.bid_lot_size1 > 0:
            self.send_amend_order(self.last_bid_id1, self.bid_lot_size1)
        if self.bid_lot_size2_pre > self.bid_lot_size2 > 0:
            self.send_amend_order(self.last_bid_id2, self.bid_lot_size2)
        if self.ask_lot_size1_pre > self.ask_lot_size1 > 0:
            self.send_amend_order(self.last_ask_id1, self.ask_lot_size1)
        if self.ask_lot_size2_pre > self.ask_lot_size2 > 0:
            self.send_amend_order(self.last_ask_id2, self.ask_lot_size2)"""
        if self.bid_lot_size1 < 0:
            self.bid_lot_size1 = 0
        if self.ask_lot_size1 < 0:
            self.ask_lot_size1 = 0
        if self.bid_lot_size2 < 0:
            self.bid_lot_size2 = 0
        if self.ask_lot_size2 < 0:
            self.ask_lot_size2 = 0

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

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        #print("on_order_book_update_message")
        
        if ask_prices[0] == 0 or bid_prices[0] == 0:
            return
        if ask_volumes[0] + bid_volumes[0] == 0:
            return

        if instrument == Instrument.ETF:
            self.etf_price.append((ask_prices[0] + bid_prices[0]) / 2)
        if instrument == Instrument.FUTURE:
            self.fut_price.append((ask_prices[0] + bid_prices[0]) / 2)

        if len(self.etf_price) > 0 and len(self.fut_price) > 0:
            self.delta.append(self.etf_price[-1] - self.fut_price[-1])
            std = np.std(self.delta)
            self.upper_rail1 = std + OFFSET1
            self.upper_rail2 = std + OFFSET2
            self.lower_rail1 = -std - OFFSET1
            self.lower_rail2 = -std - OFFSET2
        
        pos_adj = -self.position
        self.update_lot_sizes()

        if instrument == Instrument.ETF:
            new_bid_price1 = int(self.lower_rail1 + self.fut_price[-1] + pos_adj) // 100 * 100
            new_ask_price1 = int(self.upper_rail1 + self.fut_price[-1] + pos_adj) // 100 * 100
            new_bid_price2 = int(self.lower_rail2 + self.fut_price[-1] + pos_adj) // 100 * 100
            new_ask_price2 = int(self.upper_rail2 + self.fut_price[-1] + pos_adj) // 100 * 100

            if new_bid_price1 == new_bid_price2:
                new_bid_price2 -= 100
            if new_ask_price1 == new_ask_price2:
                new_ask_price2 += 100

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

            if self.last_bid_id1 == 0 and new_bid_price1 != 0 and self.position < POSITION_LIMIT and self.bid_lot_size1 > 0:
                self.last_bid_id1 = next(self.order_ids)
                self.last_bid_price1 = new_bid_price1
                self.send_insert_order(self.last_bid_id1, Side.BUY, new_bid_price1, self.bid_lot_size1, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.last_bid_id1)

            if self.last_bid_id2 == 0 and new_bid_price2 != 0 and self.position < POSITION_LIMIT and self.bid_lot_size2 > 0:
                self.last_bid_id2 = next(self.order_ids)
                self.last_bid_price2 = new_bid_price2
                self.send_insert_order(self.last_bid_id2, Side.BUY, new_bid_price2, self.bid_lot_size2, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.last_bid_id2)

            if self.last_ask_id1 == 0 and new_ask_price1 != 0 and self.position > -POSITION_LIMIT and self.ask_lot_size1 > 0:
                self.last_ask_id1 = next(self.order_ids)
                self.last_ask_price1 = new_ask_price1
                self.send_insert_order(self.last_ask_id1, Side.SELL, new_ask_price1, self.ask_lot_size1, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.last_ask_id1)

            if self.last_ask_id2 == 0 and new_ask_price2 != 0 and self.position > -POSITION_LIMIT and self.ask_lot_size2 > 0:
                self.last_ask_id2 = next(self.order_ids)
                self.last_ask_price2 = new_ask_price2
                self.send_insert_order(self.last_ask_id2, Side.SELL, new_ask_price2, self.ask_lot_size2, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.last_ask_id2)

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        #print("on_order_filled_message")
        if client_order_id in self.bids:
            self.position += volume
            self.update_lot_sizes()
            self.send_hedge_order(next(self.order_ids), Side.ASK, MIN_BID_NEAREST_TICK, volume)
        elif client_order_id in self.asks:
            self.position -= volume
            self.update_lot_sizes()
            self.send_hedge_order(next(self.order_ids), Side.BID, MAX_ASK_NEAREST_TICK, volume)

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        #print("on_order_status_message")
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
        #self.logger.info("received trade ticks for instrument %d with sequence number %d", instrument,
        #                 sequence_number)
        #print("on_trade_ticks_message")
