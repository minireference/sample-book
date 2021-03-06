#!/usr/bin/env perl -pi
use strict;
use warnings;

BEGIN {undef $/;}      # multi-line in-place substitute

# minireference LaTeX --> Softcover PolyTeX substitutions
################################################################################

# remove enumitems customizations like  [topsep=0.4em,partopsep=0.4em] 
s/\\begin\{enumerate\}\[.*\]/\\begin{enumerate}/g;
s/\\begin\{itemize\}\[.*\]/\\begin{itemize}/g;

# simpify funky negative sign
s/\\raisebox\{\.52ex\}\{\\rule\{0\.9em\}\{\.4pt\}\}/-/g;

# change figures/ to images/figures/ (softcover expectes images dir for html build)
s/\{figures/\{images\/figures/g;
s/\{problems\/figures/\{images\/problems\/figures/g;
s/\{problemsfigures/\{images\/problemsfigures/g;

# verb env for miniref code blocks
s/\\begin\{verbatimtab\}/\\begin\{verbatim\}/g;
s/\\end\{verbatimtab\}/\n\\end\{verbatim\}/g;

# handle ifthenelse marked up with special zBLOCK and ifEPUB syntax
s/\n[^\n]*
\{\{zBLOCK\}\}
(?:(?!\{\{\/zBLOCK\}\}).)*
\{\{ifEPUB\}\}
((?:(?!\{\{\/ifEPUB\}\}).)*)
[\% \t]*\{\{\/ifEPUB\}\}
(?:(?!\{\{\/zBLOCK\}\}).)*
\{\{\/zBLOCK\}\}/$1/gsx;

# vertical skip modifiers on newlines (get confused as start of displaymath)
s/\\\\\[.*?m\]/\\\\/g;

# remove all comments
s/([^\\])%.*?\n/$1/g;

# Remove broken HREF to UAM align* block
s/equation \\eqref\{UAM:v\}/velocity equation/g;

# Appendix: Answers and Solutions
s/\\showExerciseAnswers\{([^}]*)\}/\\input{99anssol\/eanswers_$1\}/g;
s/\\showExerciseSolutions\{([^}]*)\}/\\input{99anssol\/esolutions_$1\}/g;
s/\\showProblemAnswers\{([^}]*)\}/\\input{99anssol\/answers_$1\}/g;
s/\\showProblemSolutions\{([^}]*)\}/\\input{99anssol\/solutions_$1\}/g;

# Calculus problems sections
s/\\subsection\{Limits problems\}/\\large\{\\noindent\n\\textbf\{Limits problems\}\}/g;
s/\\subsection\{Derivatives problems\}/\\large\{\\noindent\n\\textbf\{Derivatives problems\}\}/g;
s/\\subsection\{Integrals problems\}/\\large\{\\noindent\n\\textbf\{Integrals problems\}\}/g;
s/\\subsection\{Sequences and series problems\}/\\noindent\n\\large\{\\textbf\{Sequences and series problems\}\}/g;

# Softsections to \section* in appendices
s/\\softsection\{/\\section\*\{/g;

# vertical skip modifiers on newlines (not supported in tables)
s/\\softchapter/\\chapter/g;
s/\\mycenteredheading/\\chapter/g;

# Special en-dash bullet list in MATH & PHYS concept map
s/\\item\[--\]/\\item/g;

# LA specific
s/\{bsmallmatrix\}/{bmatrix}/g;
s/\{vsmallmatrix\}/{vmatrix}/g;

# rm custom commands for switching TOC depth (used in functions reference sec)
s/\\addtocontents\{.*\n//g;

# remove sentences referring to index since no index in ePub and mobi
s/Consult.*thebookindex.*defined\.//g;
s/,\n.*?\{thebookindex\}//g;

# graph mini-figures in exercises and problems of the LA book
s/\$\\vcenter\{\\hbox\{\\includegraphics\[(.*?)\]\{(.*?)\}\}\}\$/\\includegraphics\[$1\]\{$2\}/g;

# print- and ipad-specific LAYOUT commands
s/\\printcp//g;
s/\\printni//g;
s/\\ipadcp//g;
s/\\ipadni//g;

