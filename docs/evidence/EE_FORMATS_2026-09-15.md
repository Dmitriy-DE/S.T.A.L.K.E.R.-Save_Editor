# Official Enhanced Edition format evidence — 2026-09-15

Enhanced Edition profiles remain visible as official release descriptors, but
they are not registered as readable formats until a real, legally usable save
sample proves the container and versioned object serialization. This prevents
the original X-Ray parser from being presented as compatible merely because a
file has a familiar extension.

## Local read-only inventory

The machine was checked through the release-aware Steam manifest and save-path
providers. The probe did not open Steam, write a save, or print personal paths.

| Official release | Steam release tree detected | Candidate save directories | Candidate files | Current parser profile |
| --- | ---: | ---: | ---: | --- |
| S.T.A.L.K.E.R. 2: Heart of Chornobyl | 0 | 0 | 0 | registered S2 profile; no local sample in automatic paths |
| Shadow of Chornobyl — Enhanced Edition | 0 | 0 | 0 | unavailable; no EE adapter registered |
| Clear Sky — Enhanced Edition | 0 | 0 | 0 | unavailable; no EE adapter registered |
| Call of Pripyat — Enhanced Edition | 0 | 0 | 0 | unavailable; no EE adapter registered |
| Original Shadow of Chornobyl | 1 | 1 | 4 `.sav` | registered original X-Ray profile |
| Original Clear Sky | 1 | 1 | 56 `.sav` | registered original X-Ray profile |
| Original Call of Pripyat | 1 | 1 | 168 `.scop` | registered original X-Ray profile |

The zero EE rows are a current-host observation, not a claim that the releases
do not create saves on Windows. Candidate extensions such as `.scs` remain
visible to desktop discovery as unsupported candidates instead of being
silently ignored.

## Public leads checked

- The [Shadow of Chornobyl EE Steam discussion](https://steamcommunity.com/app/2427410/discussions/0/528723757459612258/)
  describes EE save-side `.sav`, `.dds`, and `.info` files under a separate
  Saved Games location.
- The [Clear Sky EE Steam discussion](https://steamcommunity.com/app/2427420/discussions/0/603030907426702266/?l=ukrainian)
  contains a report involving `.scs`, which is a useful extension lead but not
  a serialization specification or a verified sample.
- Public original-X-Ray readers and OpenXRay sources were used for the
  original profiles only; they do not prove EE compatibility.

No public source located in this pass supplied a complete, license-clear EE
save fixture plus enough format detail to expose inventory mutations safely.
Therefore no Enhanced Edition format adapter, catalog, or writer is enabled.

## User-facing boundary

The Qt release selector and release-specific path settings include all three
official EE descriptors. Discovery can report an EE candidate and its exact
unsupported reason. Opening still requires a registered parser; until the
evidence row is accepted, the candidate remains read-only/unavailable rather
than being routed through an original-game parser.

Required next evidence for each EE release is a real sample (or a reproducible
public format description), exact header/compression/version identification,
wrong-game rejection, strict no-op round-trip, and then controlled game-load
validation. One EE sample must not be generalized to the other two releases.
