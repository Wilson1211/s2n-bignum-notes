LATEXMK ?= latexmk
TEX = main.tex framework.tex sampling-training-evaluation-workflows.tex independent-random-evaluation-workflow.tex
MAIN_TEX = main.tex
PDF = build/main.pdf

.PHONY: all clean
all: $(PDF)

$(PDF): $(TEX)
	mkdir -p build
	$(LATEXMK) -lualatex -interaction=nonstopmode -halt-on-error -file-line-error -outdir=build $(MAIN_TEX)

clean:
	$(LATEXMK) -C -outdir=build $(TEX)
	rmdir build
