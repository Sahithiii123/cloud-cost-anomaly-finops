.PHONY: all test

all:
	python run_all.py

test:
	python -m pytest -q