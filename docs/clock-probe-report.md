# Clock probe report (phase 0)

Date: 25 October 2026. Clock: Puri Nixie Clock, `productid` 6 (4-tube), firmware 1.40, Local API port 88.
The clock's address is not recorded here.

Method: `scripts/probe_clock.py` (GET only, one request at a time, 0.3 s apart), then a few writes, each with
the user's go-ahead and each restored afterwards. Every parameter of the clock was left at its original
value: `brightnessday` 201, `brightnessnight` 1, `transition` 2.

**Correction (same day, during phase 1):** the first version of this report said that `format`, `firmware`
and `freememory` always answer with HTML, and that writes must be JSON because a plain `1` was rejected.
Both were drawn from single requests. Repeated reads showed that the clock answers **any** parameter with its
HTML page now and then (see "Intermittent HTML answers"). The sections below are corrected.

## Intermittent HTML answers

- About one request in five (13 of 73 in a measurement with the real client, 4 of 6 for one `rssi` series)
  is answered with the clock's HTML configuration page, HTTP 200, `Content-Type: text/html`, for any
  parameter, instead of JSON. Spacing the requests 0.2, 1 or 3 seconds apart made no clear difference.
- The next identical request usually succeeds. Four attempts in a row were enough in every test:
  15 polls of four reads each all succeeded, with 13 retries.
- A request answered with HTML was not handled. After the HTML answer to the plain POST of `1`, the next read
  still gave 201. Retrying a write is safe, and the integration reads the value back anyway.

## VERIFY items of SPEC draft 1

| Item | Result |
| --- | --- |
| POST returns the new value | **Refuted.** It returns the register value, the written value minus 1 (126 gives 125, 71 gives 70, 201 gives 200, 1 gives 0). `GET` afterwards returns the written value. A no-op write of `transition` (2) returned 2, so the offset may not apply to every parameter. Decision: read back after every write. |
| Value 1 makes the tubes fully dark | **Confirmed** by the user, looking at the clock. |
| `rssi` unit | **Confirmed dBm.** `GET` gave -69, the configuration page shows "-70 dBm (Fair)". |
| `macaddr` format | **Refuted.** `GET` returns 404 "Setting not found or returned 0" every time (also in later repeats). No MAC is available. Decision: identity is `serialnumber`. |
| `customdata` order, `*` character, positions not shown on a Puri-4 | **Dropped.** Out of scope for 0.1.0; not tested. |
| Product id | 6, so a 4-tube clock. |

## Other findings

- **Plain `1` write.** `POST` of the plain integer `1` to `brightnessday` returned the HTML page and changed
  nothing; `{"value": 1}` as JSON worked. It is **not proven** that the plain form is the problem: it may have
  been the intermittent HTML answer. The client always sends JSON, which is known to work.
- **`format` and `freememory` work.** Repeated reads gave JSON: `format` 24, `freememory` about 30300. They are
  not used in 0.1.0 (scope), but nothing prevents them.
- **404 on read, every time:** `firmware`, `macaddr`, `customdatatimeout`, `time`, `hkconnectionsnumber`,
  `slotmachinemode`. The message says "Setting not found or returned 0". `firmware` is a string, which
  may be why it is not found. The firmware version (1.40) is only on the HTML page.
- **Undocumented value:** the configuration page offers `slotmachineperiod` 99 = disabled.
- **Readable and working:** `brightnessday`, `brightnessnight`, `leadingzero`, `dst`, `timezone`,
  `datedisplay`, `transition`, `slotmachineperiod`, `photonled`, `colonmode`, `rssi`, `watchdogevents`
  (read 255, possibly saturated), `currentdisplayedvalue`, `productid`, `lastntpsyncmillis` (small numbers),
  `format`, `freememory`, `connectivitymode`, `otaenabled`, `largestfreeblockheap`, `systemfirmware`,
  `serialnumber`.
- **Response times:** 17 to 98 ms, average 34 ms over the 27 probe requests.
- **Writes performed:** `transition` no-op; `brightnessday` 126, 71, 1 and back to 201. Nothing else was written.
  `reset`, `homekitreset`, `serialnumber`, `rtccalibration`, `nmstr` and `customdata*` were not written.

## Consequences for the spec (draft 2, amended)

- Identity from `serialnumber`; no MAC; no `sw_version`.
- Scope trimmed to brightness, the display switch, automatic brightness and two sensors.
- Client retries an HTML answer (4 attempts, 0.25 s apart), sends JSON and reads back after writes.
- Automatic brightness floor stays at 6.
