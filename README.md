# blue_lock_114514

This is the code repository for our team, which includes multiple versions of autotraders that were jointly conceived and implemented by lhl and ayd. The two of us started learning, brainstorming, and constantly experimenting since mid-February 2023, and finally presented these versions with different strategies.

## Main Versions
1. _cloud.py: Inspired by https://github.com/jamesdinh12/Optiver-RTG-2022 and the 'Ichimoku Cloud' strategy
2. _dyna.py: The best performed bot using both dynamic standard deviation of price spread and dynamic volumes for active orders
3. _linear.py: The best performed bot in NON-marketing neutral strategies, using linear regression
4. _maker.py: The first bot using marketing neutral strategy
5. _rail.py: A breakthough bot
6. _mult_rail: A strong bot using 2 "rails"
7. _mult_rail_pos: A bot modified from _mult_rail.py, added dynamic volumes

## Contributers
+ [LHLKEVIN013](https://github.com/LHLKEVIN0713)
+ [E70N4N](https://github.com/E70N4N)

## Development Log
1. Feb.12.2023--Feb.15.2023:
    > We figured out concepts in RTG games, like ETF, future, position, etc.
2. Feb.15.2023--Feb.16.2023:
    > Read source code in https://github.com/HackMelbourne/Optiver_RTG_Workshop \
    > Brainstorming about strategies that are NOT market neutral\
    > Implemented and testing _cta.py and _cloud.py\
    > Started using pyplot and analyzing trading data
3. Feb.17.2023:
    > Implemented _MACD.py\
    > Debugging and testing
4. Feb.18.2023--Feb.20.2030:
    > Studying strategies about VWAP and Bolling bonds\
    > Implemented _vwap.py\
    > Considering using linear regression and polynomial fitting to predict price trend
5. Feb.21.2023--Feb.24.2030:
    > Updated _vwap.py using linear regression and imported numpy
6. Feb.25.2023:
    > Implemented _linear.py, modified from _vwap.py\
    > Made a huge breakthough in TradeProfit by _linear.py
7. Feb.26.2023--Mar.03.2023:
    > Resting...
8. Mar.04.2023--Mar.07.2023:
    > Implemented _bonds.py and testing
9. Mar.08.2023--Mar.09.2023:
    > Received official email and source code\
    > **Realizing we need to hedge**\
    > Change strategy and implemented _maker.py
10. Mar.10.2023:
    > Study pair trading and implemented _makerpro.py and _makerultra.py\
    > Sudden inspiration and implemented _rail.py\
    > Ideas about dynamic "rails" and dynamic volumes of orders appeared
11. Mar.11.2023:
    > Ideas about multipule "rails" appeared and implemented _mutl_rail.py
12. Mar.12.2023:
    > Implemented _mutl_rail_pos.py(**A HUGE BREAKTHOUGH**)\
    > Implemented _triple_rail.py and tested it\
    > Found bug about dynamic volumes but failed to fix it\
    > Upload autotrader for Tournament 1
13. Mar.13.2023--Mar.15.2023:
    > Tried to fix the bug in dynamic volumes and testing
14. Mar.16.2023:
    > Implemented _dyna.py\
    > Fixed a bug in pricing in all autotraders
15. Mar.17.2023--Mar.18.2023:
    > Resting...
16. Mar.19.2023:
    > Fixed the bug in dynamic volumes in _dyna.py
