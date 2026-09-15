# X-Ray catalog evidence — 2026-09-15

This note records only aggregate read-only results. No save bytes, game
archives, private catalog dumps, or personal filesystem paths are stored in
the repository.

## Public format references

- The public [X-Ray tools DBReader](https://github.com/stalker-tools/tools/blob/main/DBReader.py)
  documents the chunked `.db/.xdb` archive layout, the 2947 regional header
  scrambler, LZ-Huffman header compression, and LZO-compressed file entries.
- The same project's [GameConfig](https://github.com/stalker-tools/tools/blob/main/GameConfig.py)
  documents the INI-like item sections, inheritance, inventory grid fields,
  and XML localization inputs.
- The implementation in `editor/xray_catalog.py` is a bounded independent
  reader. It does not import or copy the public project's code or game data.

## Local read-only probe

The installed official Steam manifests for the original trilogy were detected
on the Linux host. The probe passed the selected install root to
`XRayCatalogProvider` and did not write to the install or save directories.

| Release | Source accepted | Items | Categories | Result |
| --- | --- | ---: | --- | --- |
| Original Shadow of Chernobyl | official packed X-Ray archives | 389 | ammo 51; artifact 60; consumable 12; grenade 14; item 91; outfit 13; weapon 148 | accepted for read-only catalog extraction |
| Original Clear Sky | unpacked `gamedata` contained an `OGSM` community-mod marker | 0 | — | rejected under official-only scope |
| Original Call of Pripyat | no verified catalog resource tree found by the provider | 0 | — | catalog unavailable; save keys remain read-only |

These counts prove the reader against the current host only. They do not prove
that every retail language, patch, GOG installation, Enhanced Edition, or
unmodified Clear Sky/Call of Pripyat resource tree has the same catalog.
`prototype` remains `None`; no add/clone operation is enabled by this catalog
slice.
