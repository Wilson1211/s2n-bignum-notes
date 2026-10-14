LATEXMK ?= latexmk
TEX = framework.tex
PDF = build/framework.pdf

.PHONY: all clean
all: $(PDF)

$(PDF): $(TEX)
	mkdir -p build
	$(LATEXMK) -lualatex -interaction=nonstopmode -halt-on-error -file-line-error -outdir=build $(TEX)

clean:
	$(LATEXMK) -C -outdir=build $(TEX)
	rmdir build
