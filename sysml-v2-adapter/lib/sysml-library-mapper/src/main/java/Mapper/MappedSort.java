package Mapper;

import org.omg.sysml.lang.sysml.Type;

import java.util.*;

public class MappedSort<T extends MappedComprable<?,T>> {

	private Collection<T> nodes = new ArrayList<>();

	private Map<T, List<T>> nodeMap = new HashMap<>();
	private Map<T, Integer> nodeIndexMap = new HashMap<>();

	private List<T> sortedNodes = new ArrayList<>();

	MappedSort(Collection<T> nodes) {
		this.nodes = nodes;
		fill();
	}


	private void fill(){
		for (T node : nodes) {
			for (T other : nodes) {
				if(node == other) continue;

				if(!node.specialices(other)){
					continue;
				}
				nodeMap.computeIfAbsent(node, k -> new ArrayList<>()).add(other);
				nodeIndexMap.put(other, nodeIndexMap.getOrDefault(other, 0) + 1);

			}
		}

	}

	public List<T> sort() {
		sortedNodes = new ArrayList<>(nodes);
		sortedNodes.sort(Comparator.comparingInt(o -> nodeIndexMap.getOrDefault(o, 0)));
		return sortedNodes;
	}

	public Optional<T> get(Type element){
		List<T> hits = new ArrayList<>();
		Set<T> covered = new HashSet<>();
		for (T node : sortedNodes) {
			if(covered.contains(node) || !node.isSpecilizedBy(element) || !node.canCreate(element)){
				continue;
			}

			hits.add(node);
			covered.addAll(nodeMap.getOrDefault(node, List.of()));

		}

		if(hits.size() > 1){
			throw new IllegalStateException("Multiple hits found for element %s: %s".formatted(element.getClass().getName(), hits));
		}

		if(hits.isEmpty()) return Optional.empty();

		return Optional.of(hits.getFirst());
	}


}
