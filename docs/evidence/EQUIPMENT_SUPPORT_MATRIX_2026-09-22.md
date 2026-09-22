# Equipment support matrix — 2026-09-22

This is the release-scoped product matrix consumed by `editor.equipment` and
the Qt/web projections. It separates what can be displayed from what can be
written. `experimental` means the local codec/round-trip exists; it is not a
claim that the game accepted the edited save. `research` means observations
are displayed but the mutation is disabled. `unsupported` means no control is
offered.

| Release | Categories shown | Durability | Upgrades | Placement | Add/remove | Devices | Names/icons |
|---|---|---|---|---|---|---|---|
| S.T.A.L.K.E.R. 2 | weapon, armor, helmet, module, device, consumable, ammo, artifact, quest | experimental for source-backed weapon/armor anchors | research; installed vs available unresolved | unsupported | unsupported | NVG/binocular/detector are read-only; no fabricated condition | official loose CFG/localization; selected Zone Kit/Workshop is presentation-only |
| Shadow of Chernobyl | weapon, armor, module, device, consumable, ammo, artifact, quest | experimental | unsupported | experimental | experimental | no separate device writer | official X-Ray resources |
| Clear Sky | weapon, armor, module, device, consumable, ammo, artifact, quest | experimental | experimental | experimental | experimental | device/module semantics remain format-specific | official X-Ray resources |
| Call of Pripyat | weapon, armor, helmet, module, device, consumable, ammo, artifact, quest | experimental | experimental | experimental | experimental | device/module semantics remain format-specific | official X-Ray resources |
| Shadow of Chernobyl — Enhanced Edition | base X-Ray categories only, parser not accepted | unsupported | unsupported | unsupported | unsupported | unsupported | unavailable until an EE sample is accepted |
| Clear Sky — Enhanced Edition | base X-Ray categories only, parser not accepted | unsupported | unsupported | unsupported | unsupported | unsupported | unavailable until an EE sample is accepted |
| Call of Pripyat — Enhanced Edition | base X-Ray categories only, parser not accepted | unsupported | unsupported | unsupported | unsupported | unsupported | unavailable until an EE sample is accepted |

## Interpretation rules

- A catalog entry is metadata. It does not prove that the player owns the
  item. Owned rows come only from actor/grid/equipped observations.
- `module_states` and `upgrade_states` are `unknown` unless the save format
  proves installed/current/applicable state. S2 direct weapon references are
  shown separately from the duplicated upgrade vectors.
- NVG and binocular rows are devices. They have a placement/source field when
  the save provides one, but no durability editor. A name-table entry such as
  `Binoculars_*` or `NVG_Gen2` never creates an owned row.
- SoC's lack of confirmed upgrade editing is intentional and independent from
  Clear Sky/Call of Pripyat. Enhanced Edition profiles do not inherit an
  original-game parser or writer.
- S2 weapon condition uses one generic structural codec for every accepted
  actor-owned weapon row whose exact module/upgrade anchor is present; Kharod,
  Lavina and Skif are examples from the current corpus, not a hard-coded
  allow-list. It remains `experimental` until an edited copy is loaded and
  re-saved by the game. No module/upgrade mutation is enabled by this matrix.

The machine-readable source is [`editor/equipment_matrix.py`](../../editor/equipment_matrix.py);
the stable JSON projection is `EquipmentSupport.as_dict()` and
`EquipmentItem.as_dict()`.
