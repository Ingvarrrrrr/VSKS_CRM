"""Один модуль на магазин (kuvalda.py, regard.py, ...). Каждый объявляет
harvest(out_path, limit_categories=None, resume=False, pause_per_domain=1.0)
через tools.harvest.core.runner.harvest() + свой StoreSpec. См. README.md в
tools/harvest/ — шаблон добавления нового магазина."""
