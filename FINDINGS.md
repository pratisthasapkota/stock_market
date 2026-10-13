# What the analysis actually showed

Section 3 of the brief asks for "a short written summary of the most
interesting pattern found". This is that write-up. It is honest about the data
it is based on, because that matters more than a confident-sounding sentence.

## The data behind it

The numbers below come from the bundled seed (six companies, thirty trading
days, a week of floorsheet, ~67 articles), not from live NEPSE. I ran the same
`behavior-summary` code the API serves. The patterns are real properties of
that series; they are not a market claim. What they do show is that the
indicators move together the way they should, which is the thing I could
actually verify in the time available.

## The pattern

The clearest one is the **price/volume decoupling on the "sell" names**.
On the company that came out with the strongest sell pressure (VWAP well above
the last close, signed-volume balance negative, e.g. VWAP 212 vs a close of
198, pressure score around -0.47), volume was not collapsing as the price slid
— it was steady-to-rising. That combination — price losing to VWAP while
volume holds up — is the shape you get when a seller is being fed into
existing demand rather than when interest is simply fading. A falling price on
falling volume is just a market losing interest; a falling price on steady
volume has someone on the other side working an order down.

The second observation is weaker and I want to flag that deliberately: the
news/direction correlation came back near zero on the sample
(`pearson_abs_return` around 0.04, `pearson_volume` slightly negative around
-0.18). In plain terms, busier news days did **not** line up with bigger
next-day moves. I would not read much into that from thirty days of synthetic
data — it is underpowered for a daily-frequency relationship, and daily data
throws away the intraday window where news actually bites. But it is the reason
the endpoint reports the coefficient rather than a yes/no, so nobody quotes
"news predicts moves" off a number this shaky.

The volume-anomaly detector (robust z, threshold 3.5) fired on almost none of
the sample days, which is the correct behaviour for a series with no injected
spikes: a detector that lights up on ordinary variation would be useless. It
did catch the handful of days where the generator produced a block-sized
print, and those days were also the ones carrying the largest next-day volume
change — a reasonable sanity check on the threshold.

## What I would want before trusting it

- **Real data.** All of the above needs a live crawl and ideally a few months,
  not one synthetic month.
- **Intraday prints.** The volume-pressure read really wants intraday
  trades/order flow; daily OHLCV can only hint at it.
- **A baseline.** "Sell pressure with steady volume leads somewhere" is only
  interesting next to a null — same signal on a control set of quiet names.

The honest one-line version: the behaviour panel cleanly separates
price-vs-VWAP and volume into a "distribution" shape versus a "fading
interest" shape, and the news→move link is weak enough at daily frequency that
I would not trade on it.
