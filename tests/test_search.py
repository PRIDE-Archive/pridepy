from unittest import TestCase

from files.files import Files
from peptide.peptide import Peptide
from project.project import Project
from protein.protein import Protein
from spectra.spectra import Spectra


class TestSearch(TestCase):
    """
    A test class to test files related methods.
    """

    def test_search_projects(self):
        """
        A test method to search projects
        """
        project = Project()

        result = project.get_projects(77, 0, "ASC", "submission_date")
        assert len(result['_embedded']['projects']) == 77

        result = project.get_by_accession("PXD009476")
        assert result['accession'] == "PXD009476"

        result = project.get_reanalysis_projects_by_accession("PXD000419")
        assert result['accession'] == "PXD000419"

        result = project.get_files_by_accession("PXD009476", "", 100, 0, "ASC", "fileName")
        assert result['page']['totalElements'] == 113

        result = project.get_files_by_accession("PXD009476", "fileCategory.value==RAW", 100, 0, "ASC", "fileName")
        assert result['page']['totalElements'] == 109

        result = project.search_by_keywords_and_filters("accession:PXD008644", "", 100, 0, "", "ASC", "submission_date")
        assert len(result['_embedded']['compactprojects']) == 1

        result = project.search_by_keywords_and_filters("", "accession==PXD008644", 100, 0, "", "ASC",
                                                        "submission_date")
        assert len(result['_embedded']['compactprojects']) == 1

    def test_protein_evidences(self):
        """
        A test method to search protein evidences
        """
        search = Protein()

        result = search.protein_evidences("PXD019134", "", "", 100, 0, "ASC", "projectAccession")
        assert result['page']['totalElements'] == 144176

        result = search.protein_evidences("PXD019134", "123531", "CYSP2_HAECO", 100, 0, "ASC", "projectAccession")
        assert len(result['_embedded']['proteinevidences']) == 1

    def test_spectra_evidences(self):
        """
        A test method to search spectra evidences
        """
        search = Spectra()

        result = search.spectra_evidences("mzspec:PXD019317:sh_5282_HYK_101018_Mac_D_25mM.mzML:scan:39507:TK["
                                          "MS:1001460]PFR/2", "", "", "", "", "COMPACT", 100, 0, "ASC",
                                          "projectAccession")
        assert len(result['_embedded']['spectraevidences']) == 1

        result = search.spectra_evidences("mzspec:PXD019317:sh_5282_HYK_101018_Mac_D_25mM.mzML:scan:39507:TK["
                                          "MS:1001460]PFR/2" + "\\n" +
                                          "mzspec:PXD019317:sh_5282_HYK_101018_Mac_D_25mM.mzML:scan"
                                          ":10138:YAAMVTC[UNIMOD:4]MDEAVRNITWALKR/3", "",
                                          "", "", "", "COMPACT", 100, 0,
                                          "ASC", "projectAccession")
        assert len(result['_embedded']['spectraevidences']) == 2

    def test_peptide_evidences(self):
        """
        A test method to search peptide evidences
        """
        search = Peptide()

        result = search.peptide_evidences("PXD019134",
                                          "", "", "", "QPAYMTMKGSALSFQWIEMSSAHSLERNLAK", 100, 0, "ASC",
                                          "projectAccession")
        assert len(result['_embedded']['peptideevidences']) == 1

        result = search.peptide_evidences("", "",
                                          "gi|215496908-DECOY", "", "QPAYMTMKGSALSFQWIEMSSAHSLERNLAK", 100, 0,
                                          "ASC", "projectAccession")
        assert len(result['_embedded']['peptideevidences']) == 1

    def test_search_files(self):
        """
        A test method to search files
        """

        files = Files()

        result = files.get_all_paged_files("projectAccessions==PXD022105", "100", 0, "ASC", "submissionDate")
        assert result['page']['totalElements'] == 11
