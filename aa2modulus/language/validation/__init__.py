"""Check authored source choices against the registry facts they depend on.

Each check names the registry fact that would have to change for a choice to
become wrong, so a regenerated registry that breaks a choice fails readably.
"""
