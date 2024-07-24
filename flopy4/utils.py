def find_upper(s):
    for i in range(len(s)):
        if s[i].isupper():
            yield i


def strip(line):
    """
    Remove comments and replace commas from input text
    for a free formatted modflow input file

    Parameters
    ----------
        line : str
            a line of text from a modflow input file

    Returns
    -------
        str : line with comments removed and commas replaced
    """
    for comment_flag in ["//", "#", "!"]:
        line = line.split(comment_flag)[0]
    line = line.strip()
    return line.replace(",", " ")


class hybridproperty:
    pass
