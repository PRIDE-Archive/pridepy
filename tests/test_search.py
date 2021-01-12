from unittest import TestCase

from files.raw import RawFiles
from pride.search import Search


class TestRawFiles(TestCase):
    """
    A test class to test files related methods.
    """

    def test_search_projects(self):
        """
        A test method to search projects by keywords and filters
        """
        search = Search()

        result = search.projects("accession:PXD008644", "", 1, 0, "", "ASC", "submission_date")
        assert len(result['_embedded']['compactprojects']) == 1

        result = search.projects("", "accession==PXD008644", 1, 0, "", "ASC", "submission_date")
        assert len(result['_embedded']['compactprojects']) == 1

    def test_protein_evidences(self):
        """
        A test method to search protein evidences
        """
        search = Search()

        result = search.protein_evidences("PXD019134", "", "", 100, 0, "ASC", "projectAccession")
        assert result['page']['totalElements'] == 144176

        result = search.protein_evidences("PXD019134", "123531", "CYSP2_HAECO", 100, 0, "ASC", "projectAccession")
        assert len(result['_embedded']['proteinevidences']) == 1

    def test_spectra_evidences(self):
        """
        A test method to search spectra evidences
        """
        search = Search()

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
