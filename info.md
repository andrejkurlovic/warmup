{% if prerelease %}
## **NB!** This is a beta/pre-release version!

{% endif %}
**WarmUp Comfort+** is a modern, fully async Home Assistant integration for Warmup underfloor heating thermostats (4IE, 6IE). Configurable entirely through the UI — no YAML required.

**Features:**
- GUI setup via Settings → Integrations
- Async polling with a shared 60-second coordinator
- Climate entity with `heat`, `auto`, and `off` HVAC modes
- Sensor entities: floor temp, air temp, away/comfort/sleep/override temperatures, energy, cost
- Location mode select (auto / off / frost / timer)
- Fault indicator binary sensors (air sensor, floor sensor 1 & 2)
- Weekly schedule read: `schedule_raw` and `schedule_today` attributes on each climate entity
- `warmup.set_override` — timed temperature override
- `warmup.cancel_override` — cancel an active override
- `warmup.set_schedule` — write a weekly programme (dry_run safe-guard by default)
- `warmup.copy_current_schedule_template` — copy current schedule to HA log for editing

Please note that Warmup Plc were not involved in the creation of this software.
All Warmup trademarks belong to Warmup Plc.

For full documentation see the [README](https://github.com/andrejkurlovic/warmup).
