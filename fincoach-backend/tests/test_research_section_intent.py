from app.rag.web_research import _complete_page_window


def test_unmarked_eligibility_heading_beats_documents_for_eligibility_part():
    page = ('Education withdrawal\n\n' + 'General information. '*150 +
        '\n\nWho Can Apply\n\nMembers below age 55 with education expenses.\n\n' +
        'What You Need\n\nEducation withdrawal documents: identification and fee receipt.\n\n' + 'Footer. '*300)
    text = _complete_page_window(page, 'education withdrawal eligibility criteria', subject_query='education withdrawal')
    assert text.startswith('Who Can Apply')


def test_documents_part_selects_document_section_on_same_page():
    page = ('Education withdrawal\n\n' + 'General information. '*150 +
        '\n\nWho Can Apply\n\nMembers below age 55 with education expenses.\n\n' +
        'What You Need\n\nEducation withdrawal documents: identification and fee receipt.\n\n' + 'Footer. '*300)
    text = _complete_page_window(page, 'education withdrawal required documents', subject_query='education withdrawal')
    assert text.startswith('What You Need')


def test_malay_application_question_beats_eligibility_status_check():
    page = ('Programme overview. '*170 +
        ' 4. S: Adakah saya perlu memohon bantuan PROGRAM? J: Permohonan berasingan tidak diperlukan. '
        '5. S: Bagaimanakah cara untuk saya semak kelayakan PROGRAM? '
        'J: Semakan kelayakan boleh dibuat melalui portal rasmi dan kaedah pemakluman berikut. '
        'Application process permohonan memohon steps: check status in the portal. ' +
        'Maklumat status kelayakan. '*170)
    text = _complete_page_window(page, 'PROGRAM assistance application process', subject_query='PROGRAM')
    assert text.startswith(('4. S: Adakah', 'S: Adakah'))
    assert 'Permohonan berasingan tidak diperlukan' in text


def test_application_necessity_question_beats_status_method_question():
    page = ('Introduction. '*200 +
        ' 3. S: Adakah saya perlu memohon PROGRAM? J: Tidak. Kelayakan ditentukan secara automatik. '
        '4. S: Bagaimanakah cara untuk saya semak kelayakan PROGRAM? '
        'J: Semakan kelayakan PROGRAM boleh dibuat melalui kaedah berikut: '
        'permohonan PROGRAM, portal PROGRAM, surat PROGRAM, kaedah PROGRAM. ' + 'Footer. '*300)
    text = _complete_page_window(page, 'PROGRAM application steps', subject_query='PROGRAM')
    assert text.startswith(('3. S: Adakah', 'S: Adakah'))


def test_application_part_does_not_select_purchase_method_faq():
    page = ('Introduction. '*200 +
        ' 3. S: Adakah saya perlu memohon PROGRAM? J: Tidak. Kelayakan ditentukan secara automatik. '
        '13. S: Bagaimanakah kaedah pembelian barangan keperluan? '
        'J: Kaedah pembelian PROGRAM melibatkan barangan PROGRAM dan kedai PROGRAM. ' + 'Footer. '*300)
    text = _complete_page_window(page, 'PROGRAM application', subject_query='PROGRAM')
    assert text.startswith(('3. S: Adakah', 'S: Adakah'))


def test_eligibility_part_selects_qualification_faq_over_status_faq():
    page = ('Introduction. '*200 +
        ' 2. S: Siapakah yang layak menerima PROGRAM? J: Warganegara yang lulus program asas. '
        '6. S: Bagaimanakah cara untuk saya semak kelayakan PROGRAM? '
        'J: Semakan kelayakan PROGRAM melalui portal kelayakan PROGRAM dan surat kelayakan PROGRAM. ' + 'Footer. '*300)
    text = _complete_page_window(page, 'PROGRAM eligibility', subject_query='PROGRAM')
    assert text.startswith(('2. S: Siapakah', 'S: Siapakah'))


def test_english_qualification_question_retains_its_interrogative():
    page = ('Introduction. '*200 +
        ' 2. Q: Who is eligible? A: Approved programme recipients. '
        '6. Q: How can I check eligibility for PROGRAM? '
        'A: Check PROGRAM eligibility through the eligibility portal. ' + 'Footer. '*300)
    text = _complete_page_window(page, 'PROGRAM eligibility', subject_query='PROGRAM')
    assert text.startswith(('2. Q: Who', 'Q: Who'))
