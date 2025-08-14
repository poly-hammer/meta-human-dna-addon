from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent

TEST_FILES_FOLDER = REPO_ROOT / 'tests' / 'test_files'
EXTRA_TEST_FILES_FOLDER = REPO_ROOT / 'tests' / 'extra_test_files'
TEST_FBX_POSES_FOLDER = EXTRA_TEST_FILES_FOLDER / 'fbx' / 'poses'
TEST_JSON_POSES_FOLDER = TEST_FILES_FOLDER / 'json' / 'poses'
TEST_DNA_FOLDER = TEST_FILES_FOLDER / 'dna'

SAMPLE_DNA_FILE = TEST_DNA_FOLDER / 'ada.dna'

HEAD_DNA_FILE = TEST_DNA_FOLDER / 'ada' / 'head.dna'

BODY_DNA_FILE = TEST_DNA_FOLDER / 'ada' / 'body.dna'

TOLERANCE = {
    'neutralJointRotations': 1e-3,
    'neutralJointTranslations': 1e-3, 
    'normals': 1e-3, 
    'positions': 1e-2, # these assertions are in centimeters
    'textureCoordinates': 1e-3,
}

DNA_DEFINITION_VERSION = "defn1.1"

DNA_BEHAVIOR_VERSION = "bhvr1.1"

DNA_GEOMETRY_VERSION = "geom1.1"

# TODO: Investigate edge case where only these bone rotation values are always slightly rotated by a few degrees on the x and z.
IGNORED_BONE_ROTATIONS_ON_CALIBRATE = [
    'FACIAL_C_FacialRoot',
    'FACIAL_C_Neck1Root',
    'FACIAL_C_Neck2Root'
]
IGNORED_BONE_ROTATIONS_ON_EXPORT = [
    'FACIAL_C_FacialRoot',
    'FACIAL_C_Neck1Root',
    'FACIAL_C_Neck2Root'
]
