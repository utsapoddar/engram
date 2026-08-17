.PHONY: test demo install

install:
	python3.12 -m venv .venv
	.venv/bin/python -m pip install -e .

test:
	PYTHONPATH=src python3.12 -m unittest discover -s tests -v

demo:
	bash demo/walkthrough.sh
