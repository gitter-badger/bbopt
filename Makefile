.PHONY: install
install: build
	pip install -e .[scikit-optimize]

.PHONY: install-2
install-2: build
	python2 -m pip install -e .[scikit-optimize]

.PHONY: build
build:
	coconut setup.coco --no-tco --strict
	coconut "blackboard-source" blackboard --no-tco --strict --jobs sys

.PHONY: upload
upload: clean install
	python3 setup.py sdist bdist_wheel
	pip3 install --upgrade twine
	twine upload ./dist/*

.PHONY: setup
setup:
	pip install --upgrade setuptools pip pytest
	pip install --upgrade "coconut-develop[watch,cPyparsing]"

.PHONY: test
test: install
	pytest --strict -s ./blackboard/tests

.PHONY: test-2
test-2: install-2
	python2 -m pytest --strict -s ./blackboard/tests

.PHONY: clean
clean:
	rm -rf ./blackboard ./dist ./build
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete

.PHONY: wipe
wipe: clean
	find . -name '*.py' -delete
	rm -rf ./blackboard

.PHONY: watch
watch: install
	coconut "blackboard-source" blackboard --watch --no-tco --strict
