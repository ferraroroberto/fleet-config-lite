"""Owner checks: work that needs Roberto's validation, or a step of his before it starts.

Lite: only `block` (the comment-block format and label names) is carried so far;
it is a byte-identical port. fleet-config's `github`, `rule` and `cli` modules talk
to `gh` and are not ported, so nothing here imports them and a caller that needs
them (`chief_plan.owner_label_state`) gets an ImportError, refused before any write.
"""
