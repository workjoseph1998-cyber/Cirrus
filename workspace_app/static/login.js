/* Login only: native POST/CSRF remain untouched. No external scripts or services. */
'use strict';
(() => {
  const root=document.querySelector('body.cirrus-login');
  if(!root)return;
  const form=document.getElementById('login-form');
  if(form){
    const password=form.elements.password,toggle=form.querySelector('.login-password-toggle'),submit=form.querySelector('.login-submit'),text=form.querySelector('.login-submit-text'),status=form.querySelector('.login-form-status');
    let submitting=false;
    toggle.hidden=false;
    toggle.addEventListener('click',()=>{
      const visible=password.type==='password';
      password.type=visible?'text':'password';
      toggle.setAttribute('aria-pressed',String(visible));
      toggle.setAttribute('aria-label',visible?'Hide password':'Show password');
    });
    form.addEventListener('submit',event=>{
      if(event.defaultPrevented)return;
      if(submitting){event.preventDefault();return;}
      if(!form.checkValidity())return;
      submitting=true;submit.disabled=true;form.setAttribute('aria-busy','true');
      text.textContent='Signing in…';status.textContent='Checking your account…';
    });
    // Back/forward cache must never leave a restored form stuck in a busy state.
    addEventListener('pageshow',()=>{
      submitting=false;submit.disabled=false;form.removeAttribute('aria-busy');
      text.textContent='Sign in';status.textContent='';password.type='password';
      toggle.setAttribute('aria-label','Show password');toggle.setAttribute('aria-pressed','false');
    });
  }
  document.getElementById('login-error')?.focus();
  const canvas=document.getElementById('login-network'),ctx=canvas?.getContext('2d');
  if(!ctx)return; // Static cloud layers and the sign-in form remain usable.
  const motion=matchMedia('(prefers-reduced-motion: reduce)'),small=matchMedia('(max-width: 760px)'),fine=matchMedia('(pointer: fine)');
  const near=root.querySelector('.login-cloud-plane-near'),far=root.querySelector('.login-cloud-plane-far');
  let width=0,height=0,dpr=1,frame=0,last=0,elapsed=0,previous=0,pointer={x:.3,y:.5,inside:false},pan={x:0,y:0};
  // A bounded field of particles, plus deliberate infrastructure connections.
  const anchors=[[.05,.40],[.12,.30],[.23,.27],[.33,.35],[.44,.28],[.55,.40],[.15,.53],[.29,.52],[.42,.55],[.52,.66],[.07,.69],[.24,.72],[.38,.76]];
  const edges=[[0,1],[1,2],[2,3],[3,4],[4,5],[0,6],[1,6],[2,7],[3,7],[3,8],[4,8],[5,8],[6,7],[7,8],[8,9],[6,10],[6,11],[7,11],[8,12],[9,12],[10,11],[11,12]];
  let seed=37;const random=()=>{seed=(seed*16807)%2147483647;return(seed-1)/2147483646;};
  const particles=Array.from({length:46},()=>({x:random(),y:random(),r:.5+random()*1.15,speed:.0015+random()*.003,phase:random()*Math.PI*2}));
  function resize(){
    width=innerWidth;height=innerHeight;dpr=Math.min(devicePixelRatio||1,small.matches?1.25:1.5,1600/Math.max(width,1));
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
    if(!frame)draw();
  }
  function position(anchor,index){return{x:anchor[0]*width+Math.sin(elapsed*.09+index)*5+pan.x*.6,y:anchor[1]*height+Math.cos(elapsed*.075+index)*6+pan.y*.6};}
  function draw(){
    ctx.clearRect(0,0,width,height);
    const interactive=!motion.matches&&!small.matches&&fine.matches;
    if(interactive){pan.x+=(((pointer.x-.5)*22)-pan.x)*.045;pan.y+=(((pointer.y-.5)*15)-pan.y)*.045;}
    else{pan.x=0;pan.y=0;}
    near.style.transform=`translate3d(${pan.x}px,${pan.y}px,0)`;
    far.style.transform=`translate3d(${-pan.x*.55}px,${-pan.y*.55}px,0)`;
    if(interactive&&pointer.inside){
      const glow=ctx.createRadialGradient(pointer.x*width,pointer.y*height,0,pointer.x*width,pointer.y*height,380);
      glow.addColorStop(0,'rgba(63,174,211,.10)');glow.addColorStop(1,'rgba(63,174,211,0)');ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
    }
    const points=anchors.map(position);
    for(let i=0;i<edges.length;i++){
      if(small.matches&&i%2)continue;
      const [a,b]=edges[i],p=points[a],q=points[b];
      ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.strokeStyle='rgba(112,201,226,.12)';ctx.lineWidth=.7;ctx.stroke();
      if(!motion.matches&&!small.matches&&i%4===0){
        const t=(elapsed*.035+i*.13)%1,x=p.x+(q.x-p.x)*t,y=p.y+(q.y-p.y)*t;
        ctx.beginPath();ctx.arc(x,y,1.4,0,Math.PI*2);ctx.fillStyle='rgba(139,229,248,.6)';ctx.fill();
      }
    }
    points.forEach((p,i)=>{
      if(small.matches&&i%2)return;
      ctx.beginPath();ctx.arc(p.x,p.y,2.1,0,Math.PI*2);ctx.fillStyle='rgba(142,220,239,.55)';ctx.fill();
      ctx.beginPath();ctx.arc(p.x,p.y,5.2,0,Math.PI*2);ctx.strokeStyle='rgba(143,221,241,.13)';ctx.lineWidth=.7;ctx.stroke();
    });
    const count=small.matches?16:particles.length;
    for(let i=0;i<count;i++){
      const p=particles[i],x=(p.x*width+Math.sin(elapsed*.12+p.phase)*13+pan.x*.25),y=((p.y-elapsed*p.speed)%1+1)%1*height;
      const alpha=.15+(1+Math.sin(elapsed*.35+p.phase))*.13;
      ctx.beginPath();ctx.arc(x,y,p.r,0,Math.PI*2);ctx.fillStyle=`rgba(171,224,246,${alpha})`;ctx.fill();
    }
  }
  function tick(now){
    frame=0;
    if(document.hidden||motion.matches)return;
    const interval=small.matches?1000/15:1000/30;
    if(now-last>=interval){elapsed+=previous?Math.min((now-previous)/1000,.1):0;previous=now;last=now-((now-last)%interval);draw();}
    frame=requestAnimationFrame(tick);
  }
  function synchronize(){
    if(frame)cancelAnimationFrame(frame);frame=0;previous=0;last=0;
    root.dataset.animationPaused=String(document.hidden||motion.matches);
    if(!document.hidden){draw();if(!motion.matches)frame=requestAnimationFrame(tick);}
  }
  addEventListener('pointermove',event=>{if(event.pointerType==='mouse'&&fine.matches&&!motion.matches&&!small.matches){pointer={x:event.clientX/Math.max(width,1),y:event.clientY/Math.max(height,1),inside:true};}},{passive:true});
  document.documentElement.addEventListener('pointerleave',()=>{pointer.inside=false;pointer.x=.3;pointer.y=.5;});
  addEventListener('resize',resize,{passive:true});
  document.addEventListener('visibilitychange',synchronize);
  for(const query of [motion,small,fine])query.addEventListener('change',synchronize);
  resize();synchronize();
})();
