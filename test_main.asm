        START  1000
MAIN     JSUB   ADD
         LDA    RESULT
         STA    ANSWER
         HALT
RESULT   RESW   1
ANSWER   RESW   1
         END    MAIN
