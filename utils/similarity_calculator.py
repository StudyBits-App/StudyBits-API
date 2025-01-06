from typing import Counter

class Similarity:
    def _get_ngrams(self, text: str, n: int) -> list:
            """Generate n-grams from text."""
            words = text.lower().split()
            return [' '.join(words[i:i+n]) for i in range(len(words)-n+1)]
        
    def _get_all_ngrams(self, text: str, max_n: int = 3) -> list:
        """Get all n-grams up to max_n."""
        all_ngrams = []
        for n in range(1, min(max_n + 1, len(text.split()) + 1)):
            all_ngrams.extend(self._get_ngrams(text, n))
        return all_ngrams

    def compute_similarity(self, string1: str, string2: str) -> float:
        ngrams1 = self._get_all_ngrams(string1)
        ngrams2 = self._get_all_ngrams(string2)
        
        # Count n-grams
        counter1 = Counter(ngrams1)
        counter2 = Counter(ngrams2)
        
        # Get all unique n-grams
        all_ngrams = set(ngrams1 + ngrams2)
        
        # Calculate weighted similarity
        weights = {1: 0.3, 2: 0.3, 3: 0.4}  # Weights for different n-gram sizes
        total_score = 0
        total_weight = 0
        
        for ngram in all_ngrams:
            # Determine n-gram size
            size = len(ngram.split())
            if size > 3:
                continue
                
            # Get weight for this n-gram size
            weight = weights[size]
            
            # Calculate intersection score for this n-gram
            count1 = counter1[ngram]
            count2 = counter2[ngram]
            if count1 > 0 and count2 > 0:
                intersection = min(count1, count2)
                union = max(count1, count2)
                score = intersection / union
                total_score += score * weight
                total_weight += weight
        
        # Normalize final score
        if total_weight == 0:
            return 0.0
        
        return min(1.0, total_score / total_weight)
