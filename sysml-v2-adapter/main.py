import os
import subprocess
import shutil
import sys
import argparse

JAVA_DIR = os.path.join(os.path.dirname(__file__), "exporter")
JAR_PATH = os.path.join(JAVA_DIR, "target", "exporter-1.0-SNAPSHOT.jar")

parser = argparse.ArgumentParser(description="Converts SysML v2 twin models into deployer configs")
parser.add_argument("inputs", nargs="+", help=".sysml files or directories")
parser.add_argument("-o", "--output", default="output", help="output directory (default: output)")
args = parser.parse_args()


mvn = shutil.which("mvn")

if mvn is None:
    print("Maven (mvn) is not installed or not found in PATH. Please install Maven to proceed.")
    sys.exit(1)

subprocess.run([mvn, "-q", "-f", os.path.join(JAVA_DIR, "pom.xml"), "package", "-DskipTests"], check=True)
subprocess.run(["java", "-jar", JAR_PATH, args.output, *args.inputs], check=True)