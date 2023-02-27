from pytest import CaptureFixture

from fuzzaide.tools.argv_fuzz_cook import main


def test_argv_fuzz_cook_main(capsys: CaptureFixture):
    inp_exp = [
        (["1", "2", "hello"], "1\x002\x00hello\x00\x00"),
        (["-c", "1", "2", "hello"], "'1\\x002\\x00hello\\x00\\x00'\n"),
        (["1", "-c", "2", "hello"], "1\x00-c\x002\x00hello\x00\x00"),
    ]

    for argv, exp in inp_exp:
        main(argv)
        captured = capsys.readouterr()
        assert captured.out == exp
