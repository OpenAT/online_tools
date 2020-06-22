UPDATE public.ir_cron SET active = false;
UPDATE public.ir_mail_server SET active = false;

UPDATE public.res_company SET fa_benid = false;
UPDATE public.res_company SET fa_pin = false;
UPDATE public.res_company SET fa_login_sessionid = false;
UPDATE public.res_company SET "pvpToken_userId" = false;
UPDATE public.res_company SET "pvpToken_ou" = false;

UPDATE public.res_company SET "instance_id" = false;
UPDATE public.res_company SET "instance_base_port" = false;

/* Remove: web.base.url, email.base.url and web.freeze.url from settings */
DELETE FROM public.ir_config_parameter
WHERE
  "key" in ('web.base.url', 'web.base.url.freeze', 'email.base.url');
