# S.T.A.L.K.E.R. 2 weapon condition and module corpus — 2026-09-22

This evidence note records observations from the two newly supplied full S2
`SaveGames/Data` files and the earlier supplied Data corpus. Save bytes are
not stored in the repository. The hashes below identify the external samples
without making them fixtures.

## New samples

| Sample label | Packed bytes | Raw bytes | SHA-256 | CRC/parser |
|---|---:|---:|---|---|
| `610B5C7749C53C84312F7F841B50EE81 (1)` | 6,724,666 | 26,693,031 | `f107fb08ac972f3c20a9e59e84839d912c9ff1232963bec702802fa391124394` | CRC OK; S2 parser accepted |
| `217BB29D4FA4C87BD9F734AE755338CB` | 6,665,035 | 26,250,825 | `38f45e365440c2df6fd15032c2b06331809ae70ad5b0f72e23a89b2ea4f23796` | CRC OK; S2 parser accepted |

Both samples contain the same actor-owned Kharod handle `0x30002D01` and the
same grid Lavina handle `0x3000265C`. They are not a one-field binary pair:
the Kharod record has additional changes in state/module-related bytes, so
the condition conclusion below is a strong observed candidate, not yet a
game-accepted writer contract.

The wider local Data corpus also contains an actor-owned `Gun_SkifGun_HG`
record. Its primary weapon state is now read separately from a later embedded
Lavina snapshot that can appear inside the same broad record-end window. The
reader keeps ambiguity inside the primary state prefix read-only and accepts
only the single early candidate; this prevents the later `0.394` Lavina value
from being displayed as the pistol's condition.

## Condition observations

### Kharod

The Kharod condition candidate is the little-endian `f32` immediately before
the observed Kharod upgrade-key vector:

| Sample | Handle | Relative offset | Raw f32 | UI-equivalent |
|---|---|---:|---:|---:|
| `610... (1)` | `0x30002D01` | `record + 0x190` | `0.8845216632` | `88.45%` |
| `217...` | `0x30002D01` | `record + 0x190` | `0.9251356721` | `92.51%` |

The `92%` value agrees with the supplied in-game screenshot after normal UI
rounding. The same relative field was also observed for the earlier supplied
Kharod saves at approximately `100%`, `97.85%` and `98.18%`. This makes
`record + 0x190` a strong read anchor for this current Kharod serialization
shape.

The adjacent Kharod field at `record + 0x0C4` changes from approximately
`1.1700317` to `0.22` in the new pair. It is not treated as durability: its
range and position do not match the UI condition, and it changes alongside
other state bytes.

### Lavina

The Lavina record exposes a matching-looking condition position immediately
before its upgrade-key vector:

| Sample | Handle | Relative offset | Raw f32 | UI-equivalent |
|---|---|---:|---:|---:|
| `610... (1)` | `0x3000265C` | `record + 0x199` | `0.3941797018` | `39.42%` |
| `217...` | `0x3000265C` | `record + 0x199` | `0.3941797018` | `39.42%` |

This agrees with the supplied `39%` screenshot, but it is unchanged between
the two new files. It is therefore a corroborating read observation, not a
Lavina differential pair. A Lavina writer still needs a before/after pair or
game read-back using this shape.

The same primary-state shape is present for `Gun_SkifGun_HG`/`GunPM_HG` in the
wider corpus, including its two direct modules and three upgrade keys. It is
shown as experimental source-backed data, not as proof that every S2 weapon
serializer shares the same layout.

### Saiga/D-12

The embedded 672-entry name table contains `GuardGunD12_SG`, `GunD12_SG`,
`GunD12_MagDefault`, `TopRailD12` and several D-12 upgrade names. The supplied
files do not expose a D-12/`Saiga` actor-owned inventory row in the current
parser result. Several D-12 object records occur in the raw payload, but their
handles are not in the actor-owned list and must not be shown as the user's
weapon. The `86%` screenshot therefore needs its corresponding full Data save
for a D-12 differential check.

## Observed weapon modules

The actual owned weapon records contain module references separate from the
upgrade-key vectors.

| Weapon | Direct state/module references observed |
|---|---|
| Skif pistol (`Gun_SkifGun_HG` / `GunPM_HG` state) | `GunPM_MagIncreased`, `RU_Silen_1` |
| Kharod | `GunKharod_MagDefault`, `HP_Laser_1`, `EN_Silen_3`, `EN_GoloScope_1`, `EN_GLaunch_1` |
| Lavina | `GunLavina_MagDefault`, `TopRailLavina`, `RU_Grip_1`, `RU_X2Scope_1`, `HP_Laser_2` |

The same records also contain duplicated weapon-specific upgrade-key vectors:
15 Kharod candidates and 16 Lavina candidates in the observed shapes. The
current bytes do not prove which vector entries are installed/current and
which are available/applicable. The product must therefore show the direct
module observations separately from upgrade availability and keep upgrade
mutation read-only until a one-upgrade controlled pair identifies all affected
references.

The module vocabulary is visibly weapon-specific: Kharod has suppressor,
optical sight, grenade-launcher and laser references in this sample, while
Lavina has its own rail, grip, X2 scope, laser and weapon-specific upgrade
families. The editor must not expose one global module list for every game or
weapon.

## Device and metadata boundary

`NVG_NPC_Gen3` appears as an actor/grid item in the supplied corpus with
`kind=4` and no condition anchor; it is classified as a read-only device.
`Binoculars_02`, `Binoculars_03` and
`NVG_NPC_Gen2` are present in save-local name metadata, but their presence in
the name table alone does not prove that the player owns or equips them. No
condition editor should be attached to these devices.

The changed-save round-trip was also run with the locally built native
`ooz_encoder` from the vendored pyooz source. Editing Kharod to `0.99` and
Lavina to `0.88` produced CRC-valid compact outputs of `6,331,286` bytes from
the `6,724,666`-byte source and `6,283,080` bytes from the `6,665,035`-byte
source. The raw values and modules survived decompression round-trip; the
original Downloads files were not modified. Without that encoder the editor
now refuses to create an inflated `CC06` fallback for a compressed source.

## Acceptance status

- S2 weapon condition: **experimental/source-backed generic writer** for every
  accepted actor-owned weapon row with the validated structural anchor; the
  current corpus exercises Kharod, Lavina and Skif, but the implementation has
  no weapon-name allow-list. It is not yet game-accepted.
- S2 Lavina condition: **research / corroborating read candidate** at
  `record + 0x199`; no differential pair in these two files.
- S2 D-12 condition: **not observed in an actor-owned row** in these files.
- S2 direct weapon modules: **read-only observed metadata**.
- S2 upgrade vectors: **read-only, installed-vs-available unresolved**.
- S2 PNV/binocular condition: **not applicable until a real owned/equipped
  device record proves otherwise**.

## Required next evidence

1. Edit a copy using only the Kharod candidate, load it in the game, save it
   again and compare the game-resaved condition.
2. Supply a Lavina before/after pair where only its condition changes, or a
   D-12 pair for the `86%` state.
3. Supply a pair with exactly one module/upgrade installation changed; record
   whether the game says the module is installed, available or blocked by a
   prerequisite upgrade.

Until game load/re-save evidence passes, code may parse and stage the
source-backed weapon condition mutation, but must not claim universal S2 weapon
repair or any S2 module/upgrade writing. Modules/upgrades remain read-only.
