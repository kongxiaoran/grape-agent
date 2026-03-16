const pptxgen = require('pptxgenjs');
const html2pptx = require('/Users/kxr/learning/Mini-Agent/grape_agent/skills/document-skills/pptx/scripts/html2pptx');

async function createPresentation() {
  const pptx = new pptxgen();
  
  // Set presentation properties
  pptx.layout = 'LAYOUT_16x9';
  pptx.title = '智慧零售营销策划方案';
  pptx.author = '营销策划团队';
  pptx.company = 'Smart Retail';
  
  console.log('Creating presentation...');
  
  // Slide 1: Title
  console.log('Processing slide 1: Title...');
  await html2pptx('slide1.html', pptx);
  
  // Slide 2: Market Analysis
  console.log('Processing slide 2: Market Analysis...');
  await html2pptx('slide2.html', pptx);
  
  // Slide 3: Target Audience
  console.log('Processing slide 3: Target Audience...');
  await html2pptx('slide3.html', pptx);
  
  // Slide 4: Marketing Strategy
  console.log('Processing slide 4: Marketing Strategy...');
  await html2pptx('slide4.html', pptx);
  
  // Slide 5: Execution Plan
  console.log('Processing slide 5: Execution Plan...');
  await html2pptx('slide5.html', pptx);
  
  // Slide 6: Expected Results
  console.log('Processing slide 6: Expected Results...');
  await html2pptx('slide6.html', pptx);
  
  // Slide 7: Thank You
  console.log('Processing slide 7: Thank You...');
  await html2pptx('slide7.html', pptx);
  
  // Save the presentation
  const filename = '智慧零售营销策划方案.pptx';
  await pptx.writeFile({ fileName: filename });
  console.log(`\n✅ Presentation created successfully: ${filename}`);
  console.log('Total slides: 7');
}

createPresentation().catch(err => {
  console.error('Error creating presentation:', err);
  process.exit(1);
});
