"""Sandbox for executing commands in Docker containers."""

import docker

class Sandbox:
    """Docker-based sandbox for isolated command execution."""
    def __init__(self, image: str = "ubuntu:latest"):
        self.client = docker.from_env()
        self.container = self.client.containers.run(
            image,
            command="tail -f /dev/null",
            detach=True,
            remove=True
        )

    def run_command(self, cmd: str) -> tuple[int, str]:
        """Execute a command in the container and return (exit_code, output)."""
        exit_code, output = self.container.exec_run(cmd)
        return exit_code, output.decode("utf-8")

    def close(self):
        """Stop and remove the container."""
        self.container.stop()
