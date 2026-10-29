async (page) => {
  await page.setViewportSize({width:1440,height:720});
  const baseUrl = 'http://127.0.0.1:8000/admin';
  await page.unrouteAll({behavior:'wait'});
  await page.goto(baseUrl);
  await page.evaluate(() => localStorage.removeItem('fincoach-admin-session'));
  // UI fixtures only: real authorization and SQL are tested separately. This
  // browser check never signs in to the live project or changes live accounts.
  const admin = '11111111-1111-4111-8111-111111111111';
  const student = '22222222-2222-4222-8222-222222222222';
  const sourceId = '33333333-3333-4333-8333-333333333333';
  let revisionId = '44444444-4444-4444-8444-444444444444';
  const encoded = value => btoa(JSON.stringify(value)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
  const token = `${encoded({alg:'HS256',typ:'JWT'})}.${encoded({sub:admin,exp:Math.floor(Date.now()/1000)+3600,aud:'authenticated',role:'authenticated'})}.ui-fixture-signature`;
  const user = {id:admin,aud:'authenticated',role:'authenticated',email:'admin@example.test',created_at:'2026-09-01T00:00:00Z',app_metadata:{provider:'email'},user_metadata:{}};
  const account = {user_id:student,email:'student@example.test',display_name:'Student Demo',status:'active',role:'student',created_at:'2026-09-01T00:00:00Z',last_sign_in_at:'2026-10-01T00:00:00Z'};
  const source = {id:sourceId,title:'Emergency fund guidance',source_key:'official_budgeting_and_emergency_fund.md',archived:false,published_revision_id:revisionId,latest_revision_id:revisionId,updated_at:'2026-10-01T00:00:00Z'};
  // A full page of rows catches editors that exist below the visible screen.
  const sourceList = [source, ...Array.from({length:24}, (_, index) => ({...source,id:`source-${index}`,title:`Reviewed source ${index + 2}`,source_key:`reviewed_source_${index + 2}.md`}))];
  let detailAttempts = 0;
  let revision = {id:revisionId,title:source.title,content:'Start with a manageable savings target. Preserve essential living expenses.',source_urls:['https://example.test/official-guidance'],checked_at:'2026-09-30',status:'published',created_at:'2026-10-01T00:00:00Z',chunk_count:1,file_path:null,error_message:null};
  await page.route('https://admin-ui-test.invalid/**', route => route.fulfill({json:user}));
  await page.route('**/api/admin/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname.replace('/api/admin','');
    let result = {};
    if (path === '/config') result = {supabase_url:'https://admin-ui-test.invalid',publishable_key:'test-publishable-key',enabled:true};
    else if (path === '/login') result = {access_token:token,refresh_token:'ui-fixture-refresh'};
    else if (path === '/me') result = {user_id:admin,role:'admin'};
    else if (path === '/dashboard') result = {counts:{account_access:42,knowledge_sources:17,coaching_sessions:86,coaching_messages:254,suspended_accounts:1,failed_revisions:0},components:{ocr:'ready',embeddings:'ready'},providers:{llm_configured:true,tavily_configured:true}};
    else if (path === '/accounts') result = {items:[account,{...account,user_id:admin,email:'admin@example.test',display_name:'Administrator',role:'admin',status:'active'}],total:2};
    else if (path.startsWith('/accounts/')) {account.status=request.postDataJSON().status; result={status:account.status};}
    else if (path === '/knowledge' && request.method() === 'GET') result={items:sourceList,total:sourceList.length};
    else if (path === `/knowledge/${sourceId}`) {
      if (++detailAttempts === 1) return route.fulfill({status:500,contentType:'text/plain',body:'Internal Server Error'});
      result={source,latest:revision,revisions:[revision]};
    }
    else if (path.endsWith('/revisions')) {const body=request.postDataJSON();revisionId='55555555-5555-4555-8555-555555555555';revision={...revision,...body,id:revisionId,status:'draft',chunk_count:0};source.latest_revision_id=revisionId;result={source_id:sourceId,revision_id:revisionId};}
    else if (path.endsWith('/actions')) {const body=request.postDataJSON();if(body.action==='prepare') {revision.status='ready';revision.chunk_count=1;}if(body.action==='publish'){revision.status='published';source.published_revision_id=revisionId;}if(body.action==='archive')source.archived=true;result={source_id:sourceId};}
    else if(path==='/preview')result={chunk_count:1,excerpts:[request.postDataJSON().content],stale:false};
    else if(path==='/search')result={items:[{id:1,title:source.title,source:source.source_key,content:revision.content,similarity:.83}]};
    else if(path==='/audit')result={items:[{id:1,actor_id:admin,action:'knowledge.publish',target_type:'knowledge_source',target_id:sourceId,details:{revision_id:revisionId},created_at:'2026-10-01T00:00:00Z'}],total:1};
    else throw new Error(`Unmocked UI request: ${request.method()} ${path}`);
    await route.fulfill({json:result});
  });
  await page.goto(baseUrl);
  await page.getByRole('textbox',{name:'Password',exact:true}).fill('ui-fixture-password');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('heading',{name:'Overview',exact:true}).waitFor();
  await page.getByText('254',{exact:true}).waitFor();
  await page.screenshot({path:'admin-dashboard.png',fullPage:true});
  await page.getByRole('button',{name:/Accounts/,exact:false}).click();
  await page.getByText('Student Demo',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Suspend',exact:true}).click();
  await page.getByLabel('Reason',{exact:true}).fill('UI regression test');
  await page.getByRole('button',{name:'Confirm',exact:true}).click();
  await page.getByText('suspended',{exact:true}).waitFor();
  await page.getByRole('button',{name:/Knowledge base/}).click();
  const assertEditorVisible = async () => {
    await page.waitForFunction(() => {
      const heading = document.querySelector('.editor-panel h2');
      if (!heading) return false;
      const bounds = heading.getBoundingClientRect();
      return bounds.top >= 0 && bounds.bottom <= innerHeight && document.activeElement === heading;
    }, null, {timeout:5000});
    if (await page.getByRole('heading',{name:'Knowledge documents',exact:true}).count()) throw new Error('List obscures editor');
  };
  await page.getByRole('button',{name:'+ New document',exact:true}).click();
  await assertEditorVisible();
  await page.getByLabel('Document title',{exact:true}).fill('Unsaved source');
  // Control confirm answers inside this fixture session; the CLI manages native
  // dialogs separately, which otherwise pauses a multi-step run-code script.
  const originalConfirm = await page.evaluateHandle(() => window.confirm);
  await page.evaluate(() => { window.confirm = () => false; });
  await page.getByRole('button',{name:/Back to documents/}).click();
  if (await page.getByLabel('Document title',{exact:true}).inputValue() !== 'Unsaved source') throw new Error('Cancelled discard lost edits');
  await page.evaluate(() => { window.confirm = () => true; });
  await page.getByRole('button',{name:/Back to documents/}).click();
  await page.getByRole('heading',{name:'Knowledge documents',exact:true}).waitFor();
  await page.evaluate(original => { window.confirm = original; }, originalConfirm);
  await originalConfirm.dispose();
  await page.getByRole('button',{name:'Open',exact:true}).first().click();
  await page.getByRole('alert').filter({hasText:'The admin service is temporarily unavailable. Please retry.'}).waitFor();
  if (await page.getByRole('heading',{name:'Edit document',exact:true}).count()) throw new Error('Failed Open displayed an editor');
  await page.getByRole('button',{name:'Open',exact:true}).first().click();
  await assertEditorVisible();
  await page.getByLabel('Knowledge content',{exact:false}).fill('Updated, reviewed savings guidance. Keep essential expenses protected.');
  await page.getByRole('button',{name:'Preview chunks',exact:true}).click();
  await page.getByRole('heading',{name:'1 retrieval chunks',exact:true}).waitFor();
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await page.getByRole('button',{name:'Prepare embeddings',exact:true}).click();
  await page.getByRole('button',{name:'Publish',exact:true}).click();
  await page.getByRole('button',{name:'Confirm',exact:true}).click();
  await page.getByText('Document published.',{exact:true}).waitFor();
  await page.screenshot({path:'admin-knowledge.png',fullPage:true});
  await page.getByRole('button',{name:/Search test/}).click();
  await page.getByLabel('Knowledge search question').fill('Emergency savings');
  await page.getByRole('button',{name:'Search knowledge',exact:true}).click();
  await page.getByText('Retrieved 1 excerpts.',{exact:true}).waitFor();
  await page.getByRole('button',{name:/Audit history/}).click();
  await page.getByText('knowledge.publish',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'admin-mobile-width.png',fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw new Error('Horizontal viewport overflow');
  await page.getByRole('button',{name:/Knowledge base/}).click();
  await page.getByRole('button',{name:'+ New document',exact:true}).click();
  await assertEditorVisible();
  await page.screenshot({path:'admin-knowledge-mobile-width.png',fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw new Error('Knowledge page horizontal overflow');
  return {login:true,accounts:true,new_document_visible:true,open_document_visible:true,dirty_back_protection:true,plain_text_failure:true,document_editor:true,publish:true,search:true,audit:true,mobile_width:true,fixture_only:true};
}
