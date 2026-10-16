import unittest
from document_collection import remove_duplicate_documents, document_hash


class DocumentCollectionTests(unittest.TestCase):
    def test_category_subject_filename_changes_do_not_duplicate_original(self):
        original = {'data': b'license-photo', 'kind': 'drivers_license', 'subject': 'Owner',
                    'name': 'license.png', 'reviewed': True, 'extraction': {'fields': {'first_name': 'JANE'}}}
        duplicate = {**original, 'kind': 'passport', 'subject': 'Other', 'name': 'renamed.png'}
        passport = {'data': b'passport-photo', 'kind': 'passport', 'name': 'passport.png'}
        result = remove_duplicate_documents([original, duplicate, passport])
        self.assertEqual(result, [original, passport])
        self.assertIs(result[0], original)
        self.assertTrue(result[0]['reviewed'])

    def test_different_files_with_same_filename_are_retained(self):
        documents = [{'data': b'front', 'name': 'photo.png'}, {'data': b'back', 'name': 'photo.png'}]
        self.assertEqual(remove_duplicate_documents(documents), documents)
        self.assertNotEqual(document_hash(b'front'), document_hash(b'back'))
