from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent

TEST_FILES_FOLDER = REPO_ROOT / 'tests' / 'test_files'
EXTRA_TEST_FILES_FOLDER = REPO_ROOT / 'tests' / 'extra_test_files'
TEST_FBX_POSES_FOLDER = EXTRA_TEST_FILES_FOLDER / 'fbx' / 'poses'
TEST_JSON_POSES_FOLDER = TEST_FILES_FOLDER / 'json' / 'poses'
TEST_DNA_FOLDER = TEST_FILES_FOLDER / 'dna'

SAMPLE_DNA_FILE = TEST_DNA_FOLDER / 'ada.dna'

TOLERANCE = {
    'neutralJointRotations': 1e-3,
    'neutralJointTranslations': 1e-3, 
    'normals': 1e-3, 
    'positions': 1e-3, # these assertions are in centimeters
    'textureCoordinates': 1e-3,
}