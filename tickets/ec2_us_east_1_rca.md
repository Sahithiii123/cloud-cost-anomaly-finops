# RCA: AmazonEC2 in us-east-1 on 2025-02-10

## What happened
The unchanged service/day detector flagged this modeled event. Regional scoring identifies 2 high-confidence service-region-day candidates across the 33 original service-day alerts. These are modeled candidates, not claims about production incidents.

## Evidence
- Regional daily cost: $780.41; its prior seven-day regional baseline was $438.71.
- Regional cost z-score: 6.6362.
- Regional cost per unit: $1.705002, versus its prior 14-day regional mean of $0.989789; deviation +72.26% and unit-cost z-score 7.7872.
- Secondary service/day aggregate ratio deviation: +40.20% (not a regional measurement); service/day cost z-score 3.8692.
- Ticket cost impact is the signed regional cost difference from baseline ($341.71).

## Root-cause hypothesis
The generator explicitly multiplies EC2 cost in `us-east-1` from 2025-02-10 through 2025-02-24 by 1.9 while leaving usage unchanged. On the flagged 2025-02-10 service-region-day, the regional unit-cost measure rises 72.26% from its rolling mean. This represents a modeled rate/configuration inefficiency; it is not evidence of a production incident.

## Financial impact
Ticket-day impact versus the service-level rolling baseline: $341.71. The multi-day simulated counterfactual is in `outputs/synthetic/savings_estimate.json` and is labeled simulated.

## Recommended action
In a real account, validate instance family, purchase option, attached volumes, and resource ownership for the affected region before rightsizing or changing commitments.

## Validation step
Compare normalized cost per instance-hour before and during the modeled period; verify that cost returns to baseline without a workload or availability regression.

## Prevention
Keep resource-level CUR dimensions, enforce required tags, and alert on sustained cost-per-unit deviation only after validating metric coverage.
