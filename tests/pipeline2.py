from pipen import Pipen, Proc


class P(Proc):
    """Process"""
    input = "in"
    input_data = [1, 2, 3]
    output = "out:var:{{in.in}}"
    script = "echo 123"


class Pipeline3(Pipen):
    """The pipeline"""
    starts = P


if __name__ == "__main__":
    Pipeline3().run()
