Notes from the kickoff (Tue) — internal tooling for the data team

Present: Ana, Bo, Chen. Bo took notes, sorry for the mess

- what we want: a small service that lets analysts register a SQL query as a "metric", schedule it (hourly/daily) and get the numbers in Slack + a dashboard
- Ana: metrics run against Snowflake, read only. we must never write to the warehouse from this thing
- results should be kept ~1 year so we can chart trends
- Chen: maybe alerts? if a metric moves more than X % day over day, ping the owner. later maybe.
- DECIDED: Python, we already have the FastAPI template. Postgres for our own state. Deploy on the existing k8s cluster.
- ~200 metrics, most daily, a few hourly. queries take up to 5 min sometimes (!!) -> we need to run them in the background, not in the request
- auth: Google SSO like everything else. only the metric owner (or admins) can edit it
- Bo: what about cost? Snowflake credits — maybe cap concurrent queries to 4
- TODO Ana: ask data-eng about a read-only role
- out of scope: writing back to Snowflake, any BI-tool replacement
- team: Bo + Chen half time. want an MVP in 6 weeks
