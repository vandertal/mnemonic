"""A small English stop-word list.

Stop words are dropped from the index and from queries, but the tokenizer still
counts their positions, so phrase distances stay correct (see ``tokenizer.py``).
There is no Ukrainian list (a known limitation, see docs/labs/lab-15.md).
"""

STOPWORDS: frozenset[str] = frozenset(
    """
    a about above after again all also am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers him his how i if in into is it its just me more most my
    no nor not of off on once only or other our out over own same she should so some such than
    that the their them then there these they this those through to too under until up very was
    we were what when where which while who whom why will with would you your
    """.split()
)
