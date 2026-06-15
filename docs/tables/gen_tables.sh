latexmk -g -pdf -interaction=nonstopmode -halt-on-error wtg_parameters_table.tex
convert -density 200 wtg_parameters_table.pdf -background white -alpha remove -alpha off -quality 95 wtg_parameters_table.png

latexmk -g -pdf -interaction=nonstopmode -halt-on-error wf_layout_table.tex
convert -density 200 wf_layout_table.pdf -background white -alpha remove -alpha off -quality 95 wf_layout_table.png

latexmk -c wtg_parameters_table.tex
latexmk -c wf_layout_table.tex
