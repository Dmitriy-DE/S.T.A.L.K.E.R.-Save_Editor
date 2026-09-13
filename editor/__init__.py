"""Public editor API with lazy imports to keep codec loading acyclic."""

__all__ = [
    "BackupRecord",
    "CloudReceipt",
    "EditPlan",
    "EditorService",
    "PreparedEdit",
    "RestoreReceipt",
    "SourceRef",
    "prepare_edit",
]


def __getattr__(name: str):
    if name in {
        "CloudReceipt",
        "EditPlan",
        "PreparedEdit",
        "SourceRef",
        "BackupRecord",
        "RestoreReceipt",
    }:
        if name in {"BackupRecord", "RestoreReceipt"}:
            from .storage import BackupRecord, RestoreReceipt

            return {
                "BackupRecord": BackupRecord,
                "RestoreReceipt": RestoreReceipt,
            }[name]
        from .models import CloudReceipt, EditPlan, PreparedEdit, SourceRef

        return {
            "CloudReceipt": CloudReceipt,
            "EditPlan": EditPlan,
            "PreparedEdit": PreparedEdit,
            "SourceRef": SourceRef,
        }[name]
    if name == "prepare_edit":
        from .prepare import prepare_edit

        return prepare_edit
    if name == "EditorService":
        from .service import EditorService

        return EditorService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
