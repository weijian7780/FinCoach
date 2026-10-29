async (page) => {
  // Read-only check of the deployed website. No route fixtures, document saves,
  // uploads, preparation, publication, archive, or account changes are used.
  await page.unrouteAll({behavior:'wait'});
  await page.setViewportSize({width:1440,height:720});
  await page.goto('http://127.0.0.1:8000/admin');
  await page.getByRole('heading',{name:'Overview',exact:true}).waitFor();
  await page.getByRole('button',{name:/Knowledge base/}).click();
  await page.getByRole('button',{name:'Open',exact:true}).first().waitFor();
  const rowsBefore = await page.getByRole('row').count();
  const expectedTitle = await page.locator('tbody tr').first().locator('strong').innerText();
  const editorVisible = async () => {
    await page.waitForFunction(() => {
      const heading = document.querySelector('.editor-panel h2');
      if (!heading) return false;
      const bounds = heading.getBoundingClientRect();
      return bounds.top >= 0 && bounds.bottom <= innerHeight && document.activeElement === heading;
    }, null, {timeout:5000});
  };
  await page.getByRole('button',{name:'+ New document',exact:true}).click();
  await editorVisible();
  if (await page.getByLabel('Document title',{exact:true}).inputValue()) throw new Error('New document was not empty');
  await page.screenshot({path:'output/playwright/admin-new-document-real.png'});
  await page.getByRole('button',{name:/Back to documents/}).click();
  const detailResponse = page.waitForResponse(response => /\/api\/admin\/knowledge\/[0-9a-f-]+$/.test(new URL(response.url()).pathname));
  await page.getByRole('button',{name:'Open',exact:true}).first().click();
  const response = await detailResponse;
  if (response.status() !== 200) throw new Error(`Real document read failed: HTTP ${response.status()}`);
  await editorVisible();
  const actualTitle = await page.getByLabel('Document title',{exact:true}).inputValue();
  const contentLength = (await page.getByLabel('Knowledge content',{exact:false}).inputValue()).length;
  if (actualTitle !== expectedTitle || contentLength === 0) throw new Error('Real document content was not loaded');
  await page.screenshot({path:'output/playwright/admin-open-document-real.png'});
  await page.getByRole('button',{name:/Back to documents/}).click();
  if (await page.getByRole('row').count() !== rowsBefore) throw new Error('Read-only check changed the list');
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'+ New document',exact:true}).click();
  await editorVisible();
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile editor overflow');
  await page.screenshot({path:'output/playwright/admin-new-document-mobile-real.png'});
  await page.getByRole('button',{name:/Back to documents/}).click();
  await page.setViewportSize({width:1440,height:900});
  return {new_document_visible:true,open_document_visible:true,real_detail_http:response.status(),real_title:actualTitle,content_length:contentLength,mobile_editor_visible:true,document_count:rowsBefore-1,read_only:true,fixture_only:false};
}
