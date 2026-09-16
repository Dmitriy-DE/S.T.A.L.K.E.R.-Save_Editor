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
- Its [icon_tools.py](https://github.com/stalker-tools/tools/blob/main/icon_tools.py)
  confirms the official `ui_icon_equipment.dds` atlas and 50-pixel inventory
  grid used by the item coordinates. The repository reads that atlas locally
  when available and keeps the browser bundle metadata-only.
- The implementation in `editor/xray_catalog.py` is a bounded independent
  reader. It does not import or copy the public project's code or game data.

## Local read-only probe

The installed official Steam manifests for the original trilogy were detected
on the Linux host. The probe passed the selected install root to
`XRayCatalogProvider` and did not write to the install or save directories.

| Release | Source accepted | Items | Categories | Result |
| --- | --- | ---: | --- | --- |
| Original Shadow of Chernobyl | no complete official resource image in the detected local install; compact generated metadata fallback | 389 | ammo 51; artifact 60; consumable 12; grenade 14; item 91; outfit 13; weapon 148 | accepted for read-only catalog extraction |
| Original Clear Sky | official packed X-Ray archives; unpacked `gamedata` overlay ignored because it contained an `OGSM` community-mod marker | 417 | ammo 50; artifact 53; consumable 9; grenade 10; item 111; outfit 11; weapon 173 | accepted for read-only catalog extraction |
| Original Call of Pripyat | official packed X-Ray archives | 434 | ammo 47; artifact 57; consumable 17; grenade 14; item 134; outfit 10; weapon 155 | accepted for read-only catalog extraction |

These counts prove the reader against the current host only. They do not prove
that every retail language, patch, GOG installation, or Enhanced Edition has
the same catalog. With the installed language archives, 271 Clear Sky item
names and 144 Call of Pripyat item names are resolved from resource
localization; Shadow of Chornobyl has no local official resource image on this
host. The desktop/web compact metadata snapshot still exposes its release
catalog, but has no local atlas or prototype bytes. `prototype` remains `None`;
catalog-backed add uses the item key/family metadata together with a
same-family template already present in the selected save, rather than
copying prototype bytes from an archive. Faction counts, relation addresses,
and resource hashes are recorded separately in
[faction catalog evidence](XRAY_FACTION_CATALOG.md).

## Full-key in-memory writer probe — 2026-09-15

`.venv/bin/python tools/verify_xray_catalog.py` was run
read-only with one installed official save directory per original release.
The verifier clones every catalog key through the same serializer-family
writer helper, rebuilds one temporary container in memory, and parses it
again. It does not write an edited save or print personal paths.

| Release | Candidate saves | Catalog keys | Keys with a template | Keys visible after round-trip | Failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original Shadow of Chernobyl | 4 | 389 | 389 | 389 | 0 |
| Original Clear Sky | 56 | 417 | 417 | 417 | 0 |
| Original Call of Pripyat | 168 | 434 | 434 | 434 | 0 |

This is the strongest current evidence that the original desktop/web catalog
can stage every key in the official resource catalog using an existing save
template. It is still structural evidence: it does not prove game load/re-save,
localized display names, correct weight/grid placement, durability/upgrades,
quest uniqueness, or reference-safe removal.

## Additional installed-save corpus probe — 2026-09-16

The installed official original-trilogy save directories were scanned again in
read-only mode after the resource/catalog probe. Personal filenames, paths,
bytes, and hashes are intentionally omitted. Every detected candidate parsed
successfully and had no unresolved inventory references:

| Release | Candidate saves | Parsed | Inventory count | Unresolved references |
| --- | ---: | ---: | ---: | ---: |
| Original Shadow of Chernobyl | 6 | 6 | 5–88 | 0 |
| Original Clear Sky | 59 | 59 | 7–139 | 0 |
| Original Call of Pripyat | 171 | 171 | 28–229 | 0 |

This expands the earlier 4/56/168 writer-probe sample counts; it does not
change the historical in-memory catalog-key counts above and does not prove
that an edited output loads or persists correctly in the game.
