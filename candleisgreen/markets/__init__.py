"""Asset classes beyond US stocks: options, crypto, forex and futures.

Each module holds the instrument rules, research calculations, risk checks and an internal
simulator for one asset class. None of them sends an order to a broker. What each asset class
can do is recorded level by level in config/capabilities.yaml.
"""
