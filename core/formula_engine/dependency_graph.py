"""Dependency graph for formula execution."""
from typing import Dict, List, Set
from collections import defaultdict
import structlog

logger = structlog.get_logger()


class DependencyGraph:
    """Manages formula dependencies on tags."""
    
    def __init__(self):
        # tag_id -> [formula_ids]
        self._tag_to_formulas: Dict[int, Set[int]] = defaultdict(set)
        
        # formula_id -> [tag_ids]
        self._formula_to_tags: Dict[int, Set[int]] = defaultdict(set)
        
        self.logger = logger.bind(component="dependency_graph")
    
    def add_formula(self, formula_id: int, tag_ids: List[int]) -> None:
        """Add formula and its tag dependencies."""
        # Remove old dependencies if exists
        self.remove_formula(formula_id)
        
        # Add new dependencies
        for tag_id in tag_ids:
            self._tag_to_formulas[tag_id].add(formula_id)
            self._formula_to_tags[formula_id].add(tag_id)
        
        self.logger.info("formula_dependencies_added",
                        formula_id=formula_id,
                        tag_count=len(tag_ids))
    
    def remove_formula(self, formula_id: int) -> None:
        """Remove formula and its dependencies."""
        # Get tags this formula depends on
        tag_ids = self._formula_to_tags.get(formula_id, set())
        
        # Remove from tag mappings
        for tag_id in tag_ids:
            self._tag_to_formulas[tag_id].discard(formula_id)
            if not self._tag_to_formulas[tag_id]:
                del self._tag_to_formulas[tag_id]
        
        # Remove formula mapping
        if formula_id in self._formula_to_tags:
            del self._formula_to_tags[formula_id]
        
        self.logger.info("formula_dependencies_removed", formula_id=formula_id)
    
    def get_affected_formulas(self, tag_id: int) -> List[int]:
        """Get formulas that depend on this tag."""
        return list(self._tag_to_formulas.get(tag_id, set()))
    
    def get_formula_tags(self, formula_id: int) -> List[int]:
        """Get tags that a formula depends on."""
        return list(self._formula_to_tags.get(formula_id, set()))
    
    def get_stats(self) -> Dict:
        """Get dependency graph statistics."""
        return {
            "total_formulas": len(self._formula_to_tags),
            "total_tag_dependencies": len(self._tag_to_formulas),
            "avg_tags_per_formula": (
                sum(len(tags) for tags in self._formula_to_tags.values()) / 
                len(self._formula_to_tags) if self._formula_to_tags else 0
            ),
            "avg_formulas_per_tag": (
                sum(len(formulas) for formulas in self._tag_to_formulas.values()) / 
                len(self._tag_to_formulas) if self._tag_to_formulas else 0
            )
        }
    
    def clear(self) -> None:
        """Clear all dependencies."""
        self._tag_to_formulas.clear()
        self._formula_to_tags.clear()
        self.logger.info("dependency_graph_cleared")


# Global dependency graph instance
dependency_graph = DependencyGraph()
