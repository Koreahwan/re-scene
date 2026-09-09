import React, { useState } from 'react';

interface TopicDetailPageProps {
  topicId?: string;
  navigate?: (path: string) => void;
}

export const TopicDetailPage: React.FC<TopicDetailPageProps> = ({ navigate }) => {
  const [selectedCategory, setSelectedCategory] = useState(0);

  // 10 categories matching 1:1 Figma Frame 6
  const categories = ['All', 'Mystery', 'Crime', 'Detective', 'Clues', 'Twists', 'Characters', 'Motives', 'Evidence', 'Theories'];

  const scenes = [
    {
      reframes: [
        { num: 1, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' },
        { num: 2, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' },
        { num: 3, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' }
      ]
    },
    {
      reframes: [
        { num: 1, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' },
        { num: 2, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' },
        { num: 3, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' }
      ]
    },
    {
      reframes: [
        { num: 1, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' },
        { num: 2, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' },
        { num: 3, text: 'Detailed analysis of hidden clues and forensic connections in this scene. Spoiler protected by default.' }
      ]
    }
  ];

  return (
    <div data-layer="TopicDetailPage" style={{ width: 1920, position: 'relative', background: 'var(--Gray-0, white)', flexDirection: 'column', display: 'flex' }}>
      {/* Category Chips Container (height: 110px, paddingTop: 45px -> Y = 135..179) */}
      <div data-layer="Frame 2147227197" style={{ alignSelf: 'stretch', height: 110, boxSizing: 'border-box', paddingTop: 45, paddingLeft: 120, paddingRight: 120, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
        <div data-layer="Frame 2147227287" style={{ alignSelf: 'stretch', height: 44, boxSizing: 'border-box', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'inline-flex' }}>
          {categories.map((cat, idx) => (
            <div
              key={idx}
              onClick={() => setSelectedCategory(idx)}
              data-layer="CategoryChip"
              data-state={selectedCategory === idx ? 'Pressed' : 'Default'}
              style={{
                flex: '1 1 0',
                height: 44,
                boxSizing: 'border-box',
                paddingLeft: 14,
                paddingRight: 14,
                paddingTop: 10,
                paddingBottom: 10,
                background: selectedCategory === idx ? 'var(--Gray-700, #4A4A53)' : 'var(--Gray-100, #F2F2F5)',
                borderRadius: 20,
                justifyContent: 'center',
                alignItems: 'center',
                gap: 4,
                display: 'flex',
                cursor: 'pointer'
              }}
            >
              <div data-layer="Text" style={{ textAlign: 'center', color: selectedCategory === idx ? 'var(--Gray-0, white)' : 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>
                {cat}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Filter Row (height: 61px -> Y = 220..281) */}
      <div data-layer="Frame 2147227218" style={{ alignSelf: 'stretch', height: 61, boxSizing: 'border-box', paddingLeft: 120, paddingRight: 120, paddingTop: 20, paddingBottom: 20, borderBottom: '1px var(--Gray-100, #F2F2F5) solid', justifyContent: 'space-between', alignItems: 'center', display: 'inline-flex' }}>
        <div data-layer="Total" style={{ color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '21px', wordWrap: 'break-word' }}>
          29 Topics
        </div>
        <div data-layer="Frame 2147227219" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 10, display: 'flex' }}>
          <div data-layer="Recent" style={{ color: 'var(--Gray-800, #2D2D34)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '20px', wordWrap: 'break-word', cursor: 'pointer' }}>
            Recent
          </div>
          <div data-layer="Popular" style={{ color: 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '20px', wordWrap: 'break-word', cursor: 'pointer' }}>
            Popular
          </div>
          <div data-layer="Views" style={{ color: 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '20px', wordWrap: 'break-word', cursor: 'pointer' }}>
            Views
          </div>
        </div>
      </div>

      {/* Cards List (paddingTop: 51px -> Y = 332..1012) */}
      <div data-layer="Frame 2147227211" style={{ alignSelf: 'stretch', position: 'relative', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
        <div data-layer="Frame 2147227195" style={{ alignSelf: 'stretch', paddingLeft: 191, paddingRight: 191, paddingTop: 51, paddingBottom: 20, zIndex: 1, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
          <div data-layer="Frame 2147227293" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 60, display: 'flex' }}>
            {scenes.map((s, idx) => (
              <div
                key={idx}
                onClick={() => navigate && navigate('/posts/post_001')}
                data-layer={`Frame 214722717${9 + idx}`}
                style={{ alignSelf: 'stretch', height: 180, boxSizing: 'border-box', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 131, display: 'inline-flex', cursor: 'pointer' }}
              >
                {/* Left Column (Width 769px) */}
                <div data-layer="Frame 2147227177" style={{ width: 769, alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                  <div style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                    <div data-layer="SCENE 1 [00:00:00]" style={{ color: 'var(--Purple-500, #4C22F4)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>
                      SCENE 1 [00:00:00]
                    </div>
                    <div data-layer="TopicTitle" style={{ alignSelf: 'stretch', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '27px', wordWrap: 'break-word' }}>
                      Key narrative turning points and foreshadowed motifs in this sequence.
                    </div>
                    <div data-layer="TopicDescription" style={{ alignSelf: 'stretch', color: 'var(--Gray-500, #898992)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>
                      Connecting observable forensic premises with the subsequent reveal moment.<br />
                      Spoiler protected until revealed by viewer interaction.
                    </div>
                  </div>
                  <div data-layer="Frame 2147227285" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 13, display: 'inline-flex' }}>
                    <div style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 4, display: 'flex' }}>
                      <div style={{ width: 16, height: 16, position: 'relative', overflow: 'hidden' }}>
                        <svg width="100%" height="100%" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M1.61342 8.4761C1.52262 8.33234 1.47723 8.26046 1.45182 8.1496C1.43273 8.06632 1.43273 7.93498 1.45182 7.85171C1.47723 7.74084 1.52262 7.66896 1.61341 7.5252C2.36369 6.33721 4.59693 3.33398 8.00027 3.33398C11.4036 3.33398 13.6369 6.33721 14.3871 7.5252C14.4779 7.66896 14.5233 7.74084 14.5487 7.85171C14.5678 7.93498 14.5678 8.06632 14.5487 8.1496C14.5233 8.26046 14.4779 8.33234 14.3871 8.4761C13.6369 9.66409 11.4036 12.6673 8.00027 12.6673C4.59693 12.6673 2.36369 9.66409 1.61342 8.4761Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                          <path d="M8.00027 10.0007C9.10484 10.0007 10.0003 9.10522 10.0003 8.00065C10.0003 6.89608 9.10484 6.00065 8.00027 6.00065C6.8957 6.00065 6.00027 6.89608 6.00027 8.00065C6.00027 9.10522 6.8957 10.0007 8.00027 10.0007Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                      <div style={{ color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '400' }}>
                        1,643
                      </div>
                    </div>
                    <div style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 4, display: 'flex' }}>
                      <div style={{ width: 16, height: 16, position: 'relative' }}>
                        <svg width="100%" height="100%" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M8.2344 13.9414C8.08776 14.0193 7.91226 14.0193 7.76562 13.9414L8 13.5L8.2344 13.9414ZM13.5 5.5C13.5 4.13833 12.3442 3 10.875 3C9.78024 3 8.85288 3.63628 8.45703 4.52539C8.37672 4.70582 8.19752 4.82227 8 4.82227C7.8025 4.82227 7.62327 4.70582 7.54297 4.52539C7.14714 3.63628 6.21974 3 5.125 3C3.65582 3 2.5 4.13833 2.5 5.5C2.5 7.69698 3.875 9.57272 5.34114 10.9394C6.06596 11.6151 6.79278 12.1472 7.33919 12.5104C7.61176 12.6916 7.8383 12.8301 7.99544 12.9226C7.99686 12.9234 7.9986 12.9243 8 12.9251C8.00138 12.9243 8.00316 12.9234 8.00456 12.9226C8.1617 12.8301 8.38824 12.6916 8.66081 12.5104C9.20722 12.1472 9.93404 11.6151 10.6589 10.9394C12.125 9.57272 13.5 7.69698 13.5 5.5Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.08" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                      <div style={{ color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '400' }}>
                        1,643
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right Column (Width 638px) */}
                <div data-layer="Frame 2147227188" style={{ width: 638, alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                  {s.reframes.map((r, rIdx) => (
                    <div key={rIdx} style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'flex' }}>
                      <div style={{ alignSelf: 'stretch', justifyContent: 'space-between', alignItems: 'center', display: 'inline-flex' }}>
                        <div style={{ color: 'var(--Purple-300, #B7B3FF)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500' }}>
                          RE:SCENE {r.num} [00:00:00]
                        </div>
                        <div style={{ color: 'var(--Gray-400, #AFAFB8)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', display: 'flex', alignItems: 'center', gap: 4 }}>
                          Comments &gt;
                        </div>
                      </div>
                      <div style={{ alignSelf: 'stretch', color: 'var(--Gray-500, #898992)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px' }}>
                        {r.text}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
