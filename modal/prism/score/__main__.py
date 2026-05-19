from prism.score.scorer import cli

if __name__ == "__main__":
    import sys
    sys.exit(cli(standalone_mode=False) or 0)
