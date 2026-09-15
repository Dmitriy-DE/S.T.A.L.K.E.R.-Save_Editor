from __future__ import annotations

import hashlib

from save_format import SaveError, patch_save

from .models import EditPlan, PreparedEdit


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_edit(data: bytes, plan: EditPlan) -> PreparedEdit:
    """Apply one immutable plan after checking the analyzed source identity.

    Length-changing inventory operations and raw offsets cannot be safely
    combined.  The rejection happens before ``patch_save`` so callers cannot
    accidentally produce a partially transformed payload.
    """

    actual_sha = _sha256(data)
    if actual_sha != plan.source.sha256:
        raise SaveError(
            "Источник изменился после анализа: "
            f"SHA256 expected={plan.source.sha256} actual={actual_sha}"
        )

    if plan.raw and (plan.detach or plan.attach):
        raise SaveError(
            "Нельзя совмещать raw patch с detach/attach в одном edit plan"
        )
    if plan.adds:
        raise SaveError(
            "Добавление предметов не подтверждено для S.T.A.L.K.E.R. 2"
        )

    result = patch_save(
        data,
        new_money=plan.money,
        stack_counts=dict(plan.stacks),
        moves={handle: (x, y) for handle, x, y in plan.moves},
        detach=dict(plan.detach),
        attach_orphans={
            handle: (x, y, width, height)
            for handle, x, y, width, height in plan.attach
        },
        raw_patches=plan.raw,
    )
    output = bytes(result.data)
    return PreparedEdit(plan=plan, data=output, output_sha256=_sha256(output))
