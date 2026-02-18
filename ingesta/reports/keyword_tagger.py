"""
Keyword tagger module for extracting tags from transcription and visual analysis.

Extracts keywords from:
- Transcription text (dialogue, topics)
- Visual descriptions (scene types, objects, actions)
- Metadata (locations, people, equipment)

All processing is done locally.
"""

import re
import logging
from typing import List, Set, Dict, Optional
from dataclasses import dataclass
from collections import Counter


@dataclass
class KeywordTags:
    """Extracted keyword tags."""
    all_tags: List[str]
    dialogue_tags: List[str]
    visual_tags: List[str]
    metadata_tags: List[str]
    topic_tags: List[str]
    priority_tags: List[str]  # Most important/relevant


# Common stop words to filter out
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'between', 'among', 'is', 'are',
    'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
    'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
    'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
    'we', 'they', 'them', 'their', 'there', 'then', 'than', 'so', 'if',
    'just', 'now', 'only', 'also', 'very', 'too', 'more', 'most', 'some',
    'any', 'no', 'not', 'only', 'own', 'same', 'such', 'when', 'where',
    'why', 'how', 'all', 'each', 'few', 'much', 'many', 'other', 'another',
    'one', 'two', 'three', 'first', 'second', 'last', 'good', 'new', 'old'
}

# Visual keywords
VISUAL_KEYWORDS = {
    'wide', 'medium', 'close', 'extreme', 'shot', 'interior', 'exterior',
    'indoor', 'outdoor', 'day', 'night', 'morning', 'evening', 'static',
    'moving', 'handheld', 'tripod', 'bright', 'dark', 'shadow', 'sunlight',
    'natural', 'artificial', 'close-up', 'establishing', 'overhead',
    'aerial', 'drone', 'underwater', 'slow', 'motion', 'timelapse'
}

# Production keywords
PRODUCTION_KEYWORDS = {
    'interview', 'b-roll', 'broll', 'establishing', 'cutaway', 'reaction',
    'dialogue', 'conversation', 'talking', 'speaking', 'presentation',
    'demo', 'demonstration', 'action', 'performance', 'event', 'ceremony',
    'meeting', 'conference', 'lecture', 'class', 'workshop', 'tour',
    'documentary', 'narrative', 'commercial', 'promo', 'trailer'
}


def extract_keywords(transcription: Optional[str],
                    visual_description: Optional[str],
                    metadata: Optional[Dict] = None) -> KeywordTags:
    """
    Extract keywords from transcription, visual description, and metadata.
    
    Args:
        transcription: Transcription text
        visual_description: Visual description text
        metadata: Additional metadata dictionary
        
    Returns:
        KeywordTags with categorized keywords
    """
    logger = logging.getLogger(__name__)
    
    dialogue_tags = []
    visual_tags = []
    metadata_tags = []
    topic_tags = []
    
    # Process transcription
    if transcription:
        dialogue_tags = extract_dialogue_keywords(transcription)
        topic_tags = extract_topics(transcription)
    
    # Process visual description
    if visual_description:
        visual_tags = extract_visual_keywords(visual_description)
    
    # Process metadata
    if metadata:
        metadata_tags = extract_metadata_keywords(metadata)
    
    # Combine all tags
    all_tags_set = set(dialogue_tags + visual_tags + metadata_tags + topic_tags)
    all_tags = list(all_tags_set)
    
    # Determine priority tags (appear in multiple categories or are production keywords)
    tag_scores = Counter()
    
    for tag in dialogue_tags:
        tag_scores[tag] += 2  # Dialogue is important
    for tag in visual_tags:
        tag_scores[tag] += 1
    for tag in topic_tags:
        tag_scores[tag] += 2  # Topics are important
    for tag in metadata_tags:
        tag_scores[tag] += 1
    
    # Boost production keywords
    for tag in all_tags:
        if tag.lower() in PRODUCTION_KEYWORDS:
            tag_scores[tag] += 3
    
    # Get priority tags (top 10 by score)
    priority_tags = [tag for tag, _ in tag_scores.most_common(10)]
    
    logger.debug(f"Extracted {len(all_tags)} keywords, {len(priority_tags)} priority")
    
    return KeywordTags(
        all_tags=all_tags,
        dialogue_tags=dialogue_tags[:10],
        visual_tags=visual_tags[:10],
        metadata_tags=metadata_tags[:10],
        topic_tags=topic_tags[:10],
        priority_tags=priority_tags
    )


def extract_dialogue_keywords(text: str) -> List[str]:
    """
    Extract keywords from dialogue/transcription.
    
    Args:
        text: Transcription text
        
    Returns:
        List of keywords
    """
    # Clean and tokenize
    text = text.lower()
    
    # Remove punctuation except hyphens
    text = re.sub(r'[^\w\s-]', ' ', text)
    
    # Split into words
    words = text.split()
    
    # Filter stop words and short words
    keywords = [
        word for word in words
        if len(word) > 3 
        and word not in STOP_WORDS
        and not word.isdigit()
    ]
    
    # Count frequency
    word_counts = Counter(keywords)
    
    # Return most common (up to 15)
    return [word for word, _ in word_counts.most_common(15)]


def extract_topics(text: str) -> List[str]:
    """
    Extract topic keywords from text.
    
    Looks for:
    - Named entities (simple heuristic: capitalized words)
    - Repeated phrases
    - Technical terms
    
    Args:
        text: Input text
        
    Returns:
        List of topic keywords
    """
    topics = []
    
    # Look for capitalized phrases (potential named entities)
    capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    topics.extend([p.lower() for p in capitalized if len(p) > 3])
    
    # Look for technical terms (words with numbers, acronyms)
    technical = re.findall(r'\b[A-Z]{2,}\b|\b\w+\d+\w*\b', text)
    topics.extend([t.lower() for t in technical])
    
    # Look for repeated bigrams (2-word phrases)
    words = text.lower().split()
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    bigram_counts = Counter(bigrams)
    
    # Keep bigrams that appear multiple times
    for bigram, count in bigram_counts.most_common(5):
        if count > 1:
            # Check if meaningful (not just stop words)
            words_in_bigram = bigram.split()
            if not all(w in STOP_WORDS for w in words_in_bigram):
                topics.append(bigram)
    
    # Count and deduplicate
    topic_counts = Counter(topics)
    return [topic for topic, _ in topic_counts.most_common(10)]


def extract_visual_keywords(description: str) -> List[str]:
    """
    Extract keywords from visual description.
    
    Args:
        description: Visual description text
        
    Returns:
        List of visual keywords
    """
    if not description:
        return []
    
    # Clean and tokenize
    text = description.lower()
    words = re.findall(r'\b\w+(?:-\w+)*\b', text)
    
    # Keep visual-related words
    keywords = []
    for word in words:
        if word in VISUAL_KEYWORDS or word in PRODUCTION_KEYWORDS:
            keywords.append(word)
        elif len(word) > 3 and word not in STOP_WORDS:
            keywords.append(word)
    
    # Add production type if mentioned
    for prod_word in PRODUCTION_KEYWORDS:
        if prod_word in text:
            keywords.append(prod_word)
    
    return list(set(keywords))


def extract_metadata_keywords(metadata: Dict) -> List[str]:
    """
    Extract keywords from metadata.
    
    Args:
        metadata: Metadata dictionary
        
    Returns:
        List of metadata keywords
    """
    keywords = []
    
    # Camera model
    if 'camera_model' in metadata:
        keywords.append(metadata['camera_model'].lower().replace(' ', '-'))
    
    # Location
    if 'location' in metadata:
        loc = metadata['location'].lower().replace(' ', '-')
        keywords.append(loc)
    
    # Scene/shot/take
    if 'scene' in metadata and metadata['scene']:
        keywords.append(f"scene-{metadata['scene']}")
    if 'shot' in metadata and metadata['shot']:
        keywords.append(f"shot-{metadata['shot']}")
    if 'take' in metadata and metadata['take']:
        keywords.append(f"take-{metadata['take']}")
    
    # Reel
    if 'reel_id' in metadata and metadata['reel_id']:
        keywords.append(f"reel-{metadata['reel_id']}")
    
    # Clip type
    if 'clip_type' in metadata:
        keywords.append(metadata['clip_type'].lower())
    
    return [k for k in keywords if k]


def format_tags_for_csv(tags: KeywordTags, max_chars: int = 500) -> str:
    """
    Format tags for CSV output.
    
    Args:
        tags: KeywordTags object
        max_chars: Maximum characters for output
        
    Returns:
        Comma-separated tag string
    """
    # Prioritize priority tags
    tag_string = ', '.join(tags.priority_tags[:20])
    
    if len(tag_string) > max_chars:
        # Truncate
        truncated = tag_string[:max_chars]
        # Find last comma
        last_comma = truncated.rfind(',')
        if last_comma > 0:
            truncated = truncated[:last_comma]
        return truncated
    
    return tag_string


class KeywordTagger:
    """
    Tagger for extracting keywords from video content.
    
    Extracts tags from transcription, visual analysis, and metadata.
    All processing is done locally.
    """
    
    def tag(self, transcription: Optional[str],
           visual_description: Optional[str],
           metadata: Optional[Dict] = None) -> KeywordTags:
        """
        Extract keyword tags from video content.
        
        Args:
            transcription: Transcription text
            visual_description: Visual description
            metadata: Additional metadata
            
        Returns:
            KeywordTags with all extracted keywords
        """
        return extract_keywords(transcription, visual_description, metadata)
