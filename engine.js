(function(root){
const questions=root.GAME_CONTENT.questions;
function create(student,nickname,now=Date.now()){return {version:1,student,nickname,index:0,xp:0,score:0,attempts:{},answers:[],deadline:now+40*60000,done:false};}
function expire(s,now=Date.now()){if(now>=s.deadline)s.done=true;return s.done;}
function answer(s,id,action,reason,now=Date.now()){
 if(expire(s,now))throw Error('หมดเวลาหรือจบเกมแล้ว');
 const q=questions[s.index];if(!q||q.id!==id)throw Error('คำตอบนี้บันทึกแล้ว');
 if(!Number.isInteger(action)||!Number.isInteger(reason)||action<0||action>=q.actions.length||reason<0||reason>=q.reasons.length)throw Error('เลือกคำตอบทั้งสองขั้น');
 const ac=action===q.correct[0],rc=reason===q.correct[1],points=Number(ac)+Number(rc),exam=q.phase==='ประเมิน',count=s.attempts[id]||0;
 s.attempts[id]=count+1;const advance=exam||points===2;
 if(advance){s.index++;s.xp+=exam?points*100:count===0?150:100;s.score+=exam?points:0;s.answers.push({id,points,action,reason});}
 if(s.index===questions.length)s.done=true;
 return exam?{advance:true}:{advance,actionCorrect:ac,reasonCorrect:rc,why:q.why,card:q.card};
}
function forms(s){const u=new URL('https://forms.cloud.microsoft/Pages/ResponsePage.aspx');u.search=new URLSearchParams({id:'gnzLDoQbNkut7yCBtcESW4n4816a8PBCjVoi3DfBlG1URTFPNlgxRDFIMVRJSDMxRFkzWjZCS0hKOCQlQCNjPTEu',rf3e987bb0a78489893ef3ffd18583225:s.student,rc3482652eb70493cb348b6ae23fa8a4f:s.nickname,r8c0b4335a7724aa2bb8a137f6e12a608:String(s.score)});return u.href;}
root.GameEngine={create,answer,expire,forms};
})(globalThis);
