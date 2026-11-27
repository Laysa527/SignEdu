// Verificação automática de acessibilidade (WCAG 2.1, níveis A e AA) com a ferramenta axe-core.
// Abre cada página da plataforma num navegador automático, cria uma conta de teste e lista
// as violações encontradas. Resultado em 26/11/2026: 0 violações em todas as páginas.
//
// Como rodar (com o servidor ligado em http://127.0.0.1:5055 e banco de teste):
//   npm install playwright axe-core
//   node scripts/avaliar_acessibilidade.js
// Observação: nenhuma ferramenta automática cobre todos os critérios da WCAG; navegação por
// teclado e leitor de tela também foram conferidos manualmente.
const { chromium } = require('playwright');
const fs=require('fs'); const axe=fs.readFileSync(require.resolve('axe-core/axe.min.js'),'utf8');
(async()=>{
 const b=await chromium.launch({args:['--no-sandbox','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 const p=await b.newPage({viewport:{width:1280,height:900}});
 async function audit(nome){ await p.addScriptTag({content:axe}); const r=await p.evaluate(async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}));
   const out=r.violations.map(v=>`${v.impact} ${v.id} (${v.nodes.length}): ${v.help}`); console.log('== '+nome+' : '+out.length+' tipos'); out.forEach(o=>console.log('  '+o)); }
 await p.goto('http://127.0.0.1:5055/login.html'); await p.waitForTimeout(800); await audit('login');
 await p.click('#aba-cadastro'); await p.fill('#cadastro-nome','Teste'); await p.fill('#cadastro-email','t@e.com'); await p.fill('#cadastro-senha','senha12345'); await p.fill('#cadastro-confirmar','senha12345');
 const cb=await p.$('#cadastro-termos'); if(cb) await cb.check();
 await p.click('#form-cadastro button[type=submit]'); await p.waitForTimeout(1500);
 if (await p.isVisible('#btn-aceitar-termos')) { await p.click('#btn-aceitar-termos'); await p.waitForTimeout(1500); }
 for (const pg of ['perfil','praticar','conquistas','ranking','loja','conta','configuracoes']) { await p.goto(`http://127.0.0.1:5055/${pg}.html`); await p.waitForTimeout(1500); await audit(pg); }
 await b.close();})();
