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
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot
import gc


LOT_SIZE = 10
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
PERIOD = 26
PERIOD2 = 9
PERIOD3 = 12
PERIOD4 = 4
OFFSET = 2.4


def least_square(x: np.matrix, y: np.matrix, order: int) -> np.matrix:
    if(x.shape[0] != y.shape[0]) or (x.shape[0] != order + 1) or (y.shape[0] != order + 1):
        return np.mat([[0]])
    a = x.transpose() * x
    try:
        b = np.linalg.inv(a)
    except:
        return np.mat([[1]])
    sita = b * x.transpose() * y
    return sita 

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
        #for vwap
        self.vwap_list = list()
        self.vwap_upperband = list()
        self.vwap_lowerband = list()
        self.history_price = list()
        self.history_volume = list()
        self.history_price_aver = list()
        #for slope
        self.upperband_slope = [0,0]
        self.lowerband_slope = [0,0]
        self.upperband_slope_rev = self.lowerband_slope_rev = 0
        self.trigger = list()
        self.time = [0]
        #for poly
        self.a = list()
        self.b = list()
        self.c = list()
        #self.img = pyplot.figure(figsize=(50,50))
        self.slopes = list()
    
    def saveimg(self, name: str, a: List[int], b: List[int], cc: List[int], d: List[int]):
        fig = pyplot.figure(figsize=(min(len(a)/10,50),min(len(b)/10,50)),clear=True)
        pp = fig.add_subplot(111)
        pp.grid(True)
        ax = pp.plot(a,c='black')
        bx = pp.plot(b,c='orange')
        cx = pp.plot(cc,c='green')
        dx = pp.plot(d,c='red')
        pyplot.savefig(name,dpi=100)
        pyplot.clf()
        pyplot.close(fig)
        del fig
        gc.collect()

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
        
        if (ask_volumes[0]+bid_volumes[0]==0):
            return

        self.history_price.append((ask_prices[0]+bid_prices[0])/2)
        self.history_volume.append(ask_volumes[0]+bid_volumes[0])
        if len(self.history_price) > PERIOD2:
            self.history_price_aver.append(sum(self.history_price[-PERIOD2:])/PERIOD2)

        #calculate VWAP
        s = s2 = 0
        for i in range(-1,-min(len(self.history_price),PERIOD),-1):
            s += self.history_price[i] * self.history_volume[i]
            s2 += self.history_volume[i]
        if s2 == 0:
            vwap = 0
        else:
            vwap = int(s/s2)
        self.vwap_list.append(vwap)
        std = np.std(self.vwap_list[-PERIOD3:])
        self.vwap_upperband.append(vwap + std * OFFSET)
        self.vwap_lowerband.append(vwap - std * OFFSET)

        self.time.append(self.time[-1]+1)

        #calculate slopes
        if len(self.vwap_upperband) > PERIOD3:
            self.upperband_slope.append((self.vwap_upperband[-1]-self.vwap_upperband[-PERIOD2])/PERIOD2)
            self.lowerband_slope.append((self.vwap_lowerband[-1]-self.vwap_lowerband[-PERIOD2])/PERIOD2)
        #slope time!
        if self.upperband_slope_rev != self.lowerband_slope_rev or self.upperband_slope_rev == 0 or self.lowerband_slope_rev == 0:
            if self.upperband_slope[-2] < 0 and self.upperband_slope[-1] >= 0:
                self.upperband_slope_rev = 1
            if self.upperband_slope[-2] > 0 and self.upperband_slope[-1] <= 0:
                self.upperband_slope_rev = -1
            if self.lowerband_slope[-2] < 0 and self.lowerband_slope[-1] >= 0:
                self.lowerband_slope_rev = 1
            if self.lowerband_slope[-2] > 0 and self.lowerband_slope[-1] <= 0:
                self.lowerband_slope_rev = -1
        #bool variables
        ask = (self.upperband_slope_rev == -1) and (self.lowerband_slope_rev == -1)
        bid = (self.upperband_slope_rev == 1) and (self.lowerband_slope_rev == 1)
        """print("slopes=",self.upperband_slope[-1],' ',self.lowerband_slope[-1])
        print("revs=",self.upperband_slope_rev,' ',self.lowerband_slope_rev)
        print("ask? ",ask," bid? ",bid)"""

        if len(self.history_price_aver) <= 0:
            return
        if len(self.lowerband_slope) <= 0:
            return
        if len(self.upperband_slope) <= 0:
            return

        if instrument == Instrument.ETF:
            #price_adjustment = - (self.position // LOT_SIZE) * TICK_SIZE_IN_CENTS
            #price_adjustment = - self.upperband_slope_rev * TICK_SIZE_IN_CENTS
            #new_bid_price = bid_prices[0] + price_adjustment if bid_prices[0] != 0 else 0
            #new_ask_price = ask_prices[0] + price_adjustment if ask_prices[0] != 0 else 0
            vv = (bid_prices[0] * ask_volumes[0] + ask_prices[0] * bid_volumes[0]) / (bid_volumes[0] + ask_volumes[0])
            pos_adj = - self.position / 100 * TICK_SIZE_IN_CENTS
            vvv = (int(vv + pos_adj) // TICK_SIZE_IN_CENTS) * TICK_SIZE_IN_CENTS
            new_bid_price = int(vvv) + 300 if bid_prices[0] != 0 else 0
            new_ask_price = int(vvv) - 200 if ask_prices[0] != 0 else 0
            #print("new_bid_price=",new_bid_price,"new_ask_price=",new_ask_price)

            """if self.bid_id != 0 and new_bid_price not in (self.bid_price, 0):
                self.send_cancel_order(self.bid_id)
                self.bid_id = 0
            if self.ask_id != 0 and new_ask_price not in (self.ask_price, 0):
                self.send_cancel_order(self.ask_id)
                self.ask_id = 0

            trigger_flag = False

            if self.bid_id == 0 and (self.history_price_aver[-2] > self.vwap_list[-2] and self.history_price_aver[-1] <= self.vwap_list[-1]) and self.position + LOT_SIZE < POSITION_LIMIT:
                self.bid_id = next(self.order_ids)
                self.bid_price = new_bid_price
                self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.bid_id)
                self.upperband_slope_rev = self.lowerband_slope_rev = 0
                trigger_flag = True
                self.trigger.append(1)

            if self.ask_id == 0 and (self.history_price_aver[-2] < self.vwap_list[-2] and self.history_price_aver[-1] >= self.vwap_list[-1]) and self.position - LOT_SIZE > -POSITION_LIMIT:
                self.ask_id = next(self.order_ids)
                self.ask_price = new_ask_price
                self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.ask_id)
                self.upperband_slope_rev = self.lowerband_slope_rev = 0
                trigger_flag = True
                self.trigger.append(-1)
            
            if trigger_flag == False:
                self.trigger.append(0)"""
        
        #draw
        if len(self.history_price_aver) > PERIOD:
            self.saveimg('b.png',
                    self.history_price_aver[PERIOD:],
                    self.vwap_list[PERIOD:],
                    self.vwap_upperband[PERIOD:],
                    self.vwap_lowerband[PERIOD:])
        """if len(self.upperband_slope) > PERIOD:
            pyplot.figure(figsize=(len(self.upperband_slope[PERIOD-PERIOD3:])/10,
                            len(self.upperband_slope[PERIOD-PERIOD3:])/10),clear=True)
            pyplot.grid(True)
            pyplot.plot(self.upperband_slope[PERIOD-PERIOD3:],c='green')
            pyplot.plot(self.lowerband_slope[PERIOD-PERIOD3:],c='red')
            pyplot.savefig('c.png',dpi=100)
            pyplot.close('all')
            gc.collect()
        pyplot.scatter(self.time[1:],self.trigger)
        pyplot.savefig('trigger.png',dpi=100)
        pyplot.close('all')
        gc.collect()"""
        """if len(self.vwap_list) > 20:#and len(self.time) < 300
            self.a = self.time[-5:]
            self.b = self.vwap_list[-5:]
            params = np.polyfit(self.a,self.b,1)
            poly = np.poly1d(params)
            self.slopes.append(poly[1])

            x = np.arange(self.time[-4],self.time[-1],0.1)
            y = np.polyval(poly,x)
            pyplot.plot(x,y)
            pyplot.scatter(self.a,[i for i in self.b],c='black',s=30)
            pyplot.plot(self.a,self.history_price[-5:],c='red')
            #pyplot.scatter(self.time[-1],poly[1]/10,c='blue',s=20)
            pyplot.savefig('mm.png',dpi=100)
            #pyplot.close('all')"""

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when when of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received order filled for order %d with price %d and volume %d", client_order_id,
                         price, volume)
        if client_order_id in self.bids:
            self.position += volume
            #self.send_hedge_order(next(self.order_ids), Side.ASK, MINIMUM_BID, volume)
        elif client_order_id in self.asks:
            self.position -= volume
            #self.send_hedge_order(next(self.order_ids), Side.BID,
            #                      MAXIMUM_ASK//TICK_SIZE_IN_CENTS*TICK_SIZE_IN_CENTS, volume)

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
