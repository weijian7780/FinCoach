
-- Receipt data survives actual snapshot + restore, including more than 8 long items.
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
insert into public.transactions(id,user_id,category_id,amount,transaction_date,description,source,receipt_image_path,receipt_items)
select '00000000-0000-0000-0000-000000000050',auth.uid(),90001,30,'2026-10-15','Scanned receipt','Merchant',auth.uid()::text || '/receipt.jpg',
  jsonb_agg(jsonb_build_object('description',repeat('Long item description ',20)||n,'amount',1,'modifiers',jsonb_build_array('no ice','large')) order by n)
from generate_series(1,30) n;
insert into public.backups(id,user_id,backup_type,status,file_name) values('00000000-0000-0000-0000-000000000060',auth.uid(),'manual','completed','test.json');
do $$declare snapshot jsonb; original jsonb; legacy jsonb;
begin
  snapshot:=public.financial_backup_snapshot_v2();
  original:=snapshot->'transactions'->0->'receipt_items';
  perform public.test_assert(jsonb_array_length(original)=30,'snapshot retains all receipt items');
  perform private.restore_financial_backup_v1(jsonb_build_object('schemaVersion',1,'userId',auth.uid(),'data',snapshot),'00000000-0000-0000-0000-000000000060');
  perform public.test_assert((select receipt_items=original from public.transactions where id='00000000-0000-0000-0000-000000000050'),'all receipt descriptions and modifiers round trip');
  legacy:=jsonb_set(snapshot,'{transactions,0}',(snapshot->'transactions'->0)-'receipt_items');
  perform private.restore_financial_backup_v1(jsonb_build_object('schemaVersion',1,'userId',auth.uid(),'data',legacy),'00000000-0000-0000-0000-000000000060');
  perform public.test_assert((select receipt_items='[]'::jsonb from public.transactions where id='00000000-0000-0000-0000-000000000050'),'legacy receipt backups remain compatible');
end$$;

-- Reject malformed structured items before they can break the detail screen.
set role authenticated;
do $$begin
  begin
    update public.transactions set receipt_items='["invalid item"]' where id='00000000-0000-0000-0000-000000000050';
    raise exception 'invalid receipt accepted';
  exception when check_violation then null;end;
end$$;
reset role;
