#!/usr/bin/env perl -pi
# multi-line in place substitute
use strict;
use warnings;

BEGIN {undef $/;}     

# noBSmath --> PolyTeX   substitutions
# #################################################################### 
 
# TODO: automatically replace tables




# remove enumitems customizations like  [topsep=0.4em,partopsep=0.4em] 
s/\\begin\{enumerate\}\[.*\]/\\begin{enumerate}/g;
s/\\begin\{itemize\}\[.*\]/\\begin{itemize}/g;

# funky negative sign
s/\\raisebox\{\.52ex\}\{\\rule\{0\.9em\}\{\.4pt\}\}/-/g;

# change figures/ to images/figures/
s/\{figures/\{images\/figures/g;
s/\{problems\/figures/\{images\/problems\/figures/g;

# get rid of \intertext and \shortintertext
#s/\\\\ *\n*([ \t]*)\\intertext\{([^}]*)\}/\n$1\\end{align\*}\n$1$2\n$1\\begin{align\*}/gs;
#s/\\\\ *\n*([ \t]*)\\shortintertext\{([^}]*)\}/\n$1\\end{align\*}\n$1$2\n$1\\begin{align\*}/gs;

# verb env for miniref code blocks
s/\\begin\{verbatimtab\}/\\begin\{verbatim\}/g;
s/\\end\{verbatimtab\}/\n\\end\{verbatim\}/g;

# cleanup exercise sections that were oncatenated using cat
#s/\\input\{problems\/chapter1_solving_systems_of_lin_eqns_exercises\.tex\}//g;
#s/\\input\{problems\/chapter2_problems\.tex\}//g;
#s/\\input\{problems\/chapter4_problems\.tex\}//g;
#s/\\input\{problems\/chapter4_momentum_exercises\.tex\}//g;
#s/\\input\{problems\/chapter4_energy_exercises\.tex\}//g;
#s/\\input\{problems\/chapter5_problems\.tex\}//g;
#s/\\input\{problems\/chapter5_limits_exercises\.tex\}//g;
#s/\\input\{problems\/chapter5_volumes_of_revolution_exercises\.tex\}//g;

# replace .pdf figures with .png
s/\\includegraphics([^}]*).pdf\}/\\includegraphics$1.png\}/g;
# remove options on \includegraphics
# s/\\includegraphics\[[^\]]*\]\{/\\includegraphics\{/g;
# TODO: preserve width props?
#
# handle ifthenelse marked up with special zBLOCK and ifEPUB syntax
s/\n[^\n]*
\{\{zBLOCK\}\}
(?:(?!\{\{\/zBLOCK\}\}).)*
\{\{ifEPUB\}\}
((?:(?!\{\{\/ifEPUB\}\}).)*)
[\% \t]*\{\{\/ifEPUB\}\}
(?:(?!\{\{\/zBLOCK\}\}).)*
\{\{\/zBLOCK\}\}/$1/gsx;

# remove all comments
s/([^\\])%.*?\n/$1/g;
# change %= to % = because Polytexnic uses %= for pass-through comments...
# s/\%=/% =/g;

# add centering to wrapfigures
# s/\\begin\{wrapfigure\}\{.*?\}\{.*?\}/\\begin\{figure\}[ht] \\centering/g;
s/\\begin\{wrapfigure\}(\[.*?\])?(\{.*?\})+/\\begin\{figure\} \\centering/g;
s/\\end\{wrapfigure\}/\\end\{figure\}/g;

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

