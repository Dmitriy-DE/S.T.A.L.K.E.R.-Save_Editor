"""Public editor API with lazy imports to keep codec loading acyclic."""

__all__ = ["CloudReceipt", "EditPlan", "PreparedEdit", "SourceRef", "prepare_edit"]


def __getattr__(name: str):
    if name in {"CloudReceipt", "EditPlan", "PreparedEdit", "SourceRef"}:
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
