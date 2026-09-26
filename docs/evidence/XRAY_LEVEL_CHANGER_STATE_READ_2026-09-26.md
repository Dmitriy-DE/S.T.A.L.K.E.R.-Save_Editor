# X-Ray level changer STATE packet research — 2026-09-26

## Scope

Repository review found no parser or test for `all.spawn` level-changer objects.
`editor.xray_catalog.read_xray_asset()` returns bytes from an installed asset
archive; it does not decode the spawn file or dispatch object state by class.

This research records and tests only the class-specific suffix read by
`CSE_ALifeLevelChanger::STATE_Read`. It does not establish the `all.spawn`
container/object framing or locate the end of the inherited
`CSE_ALifeSpaceRestrictor` state.

## Source and field order

The reference is the public OpenXRay `xray-16` source pinned at commit
[`eda9503`](https://github.com/OpenXRay/xray-16/blob/eda9503dd4056e52fa9cee58dfae53f530cd5b9a/src/xrServerEntities/xrServer_Objects_ALife.cpp#L650-L742).
This is an OpenXRay implementation reference, not proof that every original
GSC game build uses the same object version or packet layout.

`CSE_ALifeSpaceRestrictor::STATE_Read` first reads its inherited dynamic-object
state, then `cform_read`, and reads the restrictor type only when
`m_wVersion > 74`. `CSE_ALifeLevelChanger::STATE_Read` then reads the following
class-specific suffix. The version in these conditions is the entity's
`m_wVersion`, not the save-container or actor-spawn version.

| Entity version | Suffix fields read | Interpretation |
|---|---|---|
| `< 34` | two `u32`, then two NUL-terminated strings | The two integers are discarded by the source; the parser leaves destination ids and vectors unknown. |
| `>= 34` | `u16`, `u32`, three `f32`, then direction | `m_tNextGraphID`, `m_dwNextNodeID`, destination position. |
| `34…53` | one `f32` direction value | Source stores it as the y component of `m_tAngles`; the other components are zero. |
| `> 53` | three `f32` direction values | Full `m_tAngles` vector. |
| all versions | two NUL-terminated strings | `m_caLevelToChange` (destination level name), then `m_caLevelPointToChange` (destination point name). |
| `> 116` | one `u8` | `m_bSilentMode`, interpreted as false/true. |

The code in `editor.xray_level_changer.parse_level_changer_state_suffix()`
implements only that suffix. Its caller must locate the suffix boundary and
provide the entity version. It also returns the number of consumed bytes so a
future object parser can account for any remaining state bytes explicitly.

## Test evidence

`tests/test_xray_level_changer.py` builds synthetic packet suffixes and checks
versions 118, 53, and 33, plus rejection of a truncated version-118 suffix.
These tests verify this decoder against the cited field order; they do not
prove game acceptance or match a real installed `all.spawn` asset. The test
names are ASCII; non-ASCII string encoding is not established here.

## Remaining evidence gap

No personal game assets were used or committed. A future anchor-builder change
still needs to establish the full `all.spawn` record framing, object class and
version source, inherited-state boundary, and release-specific compatibility
before it can safely emit destination points. This PR intentionally does not
add `tools/build_relocation_anchors.py` or `web/relocation_anchors.json`.
